"""Worker to send jobs to QPU"""

import asyncio
import logging
from contextlib import contextmanager
from datetime import datetime

from warden.lib.config import Config
from warden.lib.qpu_client import (
    JobCancelationError,
    JobStatus,
    QPUClient,
    QPUClientRequestError,
    QPUJobInfo,
)
from warden.scheduler.errors import QPUDownError
from warden.scheduler.types import JobUpdate, JobUpdateQueue

logger = logging.getLogger(__name__)


class JobExecutionTracker:
    """Handles current job status and sends updates to db"""

    def __init__(self, queue: JobUpdateQueue):
        self.queue = queue
        self.qpu_job_info: QPUJobInfo | None = None

        self._status: JobStatus = "PENDING"
        self._log_buffer: list[str] = []

    @property
    def status(self) -> JobStatus:
        return self._status

    @property
    def job(self) -> QPUJobInfo:
        if self.qpu_job_info is None:
            raise RuntimeError("JobExecutionTracker has no previous QPUJobInfo")
        return self.qpu_job_info

    async def update_job(self, qpu_job_info: QPUJobInfo):
        self.qpu_job_info = qpu_job_info
        self._status = qpu_job_info.status
        await self.push_update()

    async def to_error(self):
        self._status = "ERROR"
        await self.push_update()

    def is_error(self) -> bool:
        return self.status == "ERROR"

    def log(self, msg: str) -> None:
        self._log_buffer.append(msg + "\n")

    async def push_update(self):
        """Push update of job execution to db commit task through queue"""
        new_logs = "".join(self._log_buffer)
        self._log_buffer = []

        update = JobUpdate(
            status=self.status,
            new_logs=new_logs,
        )
        if self.qpu_job_info is not None:
            update.backend_id = str(self.qpu_job_info.uid)
            update.started_at = self.qpu_job_info.start_datetime
            update.ended_at = self.qpu_job_info.end_datetime
            update.result = self.qpu_job_info.result
        await self.queue.put(update)


class JobLoggingHandler(logging.Handler):
    """Emits job's logs in db through the JobHandler"""

    def __init__(self, job_tracker: JobExecutionTracker, level=0):
        super().__init__(level)
        self.job_tracker = job_tracker

    def emit(self, record):
        try:
            msg = self.format(record)
            self.job_tracker.log(msg.strip())
        except Exception:
            self.handleError(record)


class JobFilter(logging.Filter):
    """Filter logs that should not be sent to the job's logs in db"""

    def filter(self, record):
        """Send logs to be pushed to db by default"""
        return getattr(record, "to_db", True)


@contextmanager
def record_logs(job_tracker: JobExecutionTracker):
    """Setups logger for current job executions recording of logs"""

    # User-visible logs should only be >= INFO level
    job_log_handler = JobLoggingHandler(job_tracker, logging.INFO)
    job_log_handler.addFilter(JobFilter())
    job_log_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    )
    logger.addHandler(job_log_handler)
    try:
        yield
    finally:
        logger.removeHandler(job_log_handler)


class LocalQPUWorker:
    """Local Pasqal QPU Worker"""

    def __init__(self, conf: Config):
        self.conf_sched = conf.scheduler
        self.qpu_client = QPUClient(qpu_conf=conf.qpu)

    @property
    def operational_status(self):
        return self.qpu_client.get_operational_status()

    @property
    def is_operational(self):
        return self.operational_status == "UP"

    @staticmethod
    def is_timed_out(timeout_s: int | float, start: datetime) -> bool:
        if timeout_s < 0:
            return False
        return (datetime.now() - start).total_seconds() > timeout_s

    async def execute_job(
        self,
        queue: JobUpdateQueue,
        nb_run: int,
        sequence: str,
        batch_id: str | None = None,
    ) -> None:
        """Execute job on the QPU"""

        job_tracker = JobExecutionTracker(queue)
        with record_logs(job_tracker):
            await self.poll_qpu(job_tracker)
            if job_tracker.is_error():
                return
            logger.info("QPU is operational")

            await self.create_job(
                job_tracker=job_tracker,
                nb_run=nb_run,
                sequence=sequence,
                batch_id=batch_id,
            )
            if job_tracker.is_error():
                return
            logger.info("Job created on QPU")

            await self.await_job_execution(job_tracker)
            if job_tracker.status not in ("CANCELED", "ERROR"):
                logger.info("Job execution done")

            # Flush last updates before return
            await job_tracker.push_update()

    async def poll_qpu(self, job_tracker: JobExecutionTracker) -> None:
        """Check the QPU status"""
        try:
            polling_start = datetime.now()
            while not self.is_operational:
                if self.is_timed_out(
                    self.conf_sched.qpu_polling_timeout_s, polling_start
                ):
                    raise QPUDownError
                logger.info(
                    f"QPU not operational, will try again in {self.conf_sched.qpu_polling_interval_s}s",
                    extra={"to_db": False},
                )
                await asyncio.sleep(self.conf_sched.qpu_polling_interval_s)
        except QPUDownError:
            logger.error(
                "QPU not operational for more than "
                f"{self.conf_sched.qpu_polling_timeout_s} seconds. Aborting. "
                "Submit when the QPU's status is 'UP'. "
            )
            await job_tracker.to_error()
        except QPUClientRequestError as e:
            logger.error(f"Failed polling QPU status: {e}")
            await job_tracker.to_error()

    async def create_job(
        self,
        job_tracker: JobExecutionTracker,
        nb_run: int,
        sequence: str,
        batch_id: str,
    ) -> None:
        """Create the job on the QPU"""
        try:
            qpu_job_info = self.qpu_client.create_job(
                nb_run=nb_run,
                abstract_sequence=sequence,
                batch_id=batch_id,
            )

            await job_tracker.update_job(qpu_job_info)
        except QPUClientRequestError as e:
            logger.error(f"Failed creating job: {e}")
            await job_tracker.to_error()

    async def await_job_execution(self, job_tracker: JobExecutionTracker) -> None:
        """Polling the job status until completion, error, or cancellation"""
        polling_start = datetime.now()
        await self._get_job_poll(job_tracker)
        while job_tracker.status not in ("ERROR", "DONE", "CANCELED"):
            if self.is_timed_out(self.conf_sched.job_polling_timeout_s, polling_start):
                logger.warning(
                    f"Job timed out (max {self.conf_sched.job_polling_timeout_s} s). "
                    "Terminating its associated QPU job "
                    f"{job_tracker.job.uid}."
                )
                try:
                    qpu_job_info = self.qpu_client.cancel_job(job_tracker.job)
                    await job_tracker.update_job(qpu_job_info)
                except (JobCancelationError, QPUClientRequestError) as e:
                    logger.error(f"Failed cancelling job: {e}")
                    await job_tracker.to_error()
                    continue
                logger.info("Job cancellation done")
                continue
            await asyncio.sleep(self.conf_sched.job_polling_interval_s)
            await self._get_job_poll(job_tracker)

    async def _get_job_poll(self, job_tracker: JobExecutionTracker) -> None:
        try:
            # When polling the job status, we set no_retry=True as we are
            # in the job polling loop that will handle the retry of the requests
            # until an eventual timout of the job
            qpu_job_info = self.qpu_client.get_job(job_tracker.job, no_retry=True)
            await job_tracker.update_job(
                qpu_job_info,
            )
            logger.info(f"Job status: {job_tracker.status}", extra={"to_db": False})
        except QPUClientRequestError as e:
            logger.warning(
                f"Got an error while polling job status: {e}."
                f"Continuing polling, last known job status: {job_tracker.status}.",
                extra={"to_db": False},
            )
