"""Worker to send jobs to QPU"""

import asyncio
import logging
from asyncio import Queue
from datetime import datetime

from warden.lib.config import Config
from warden.lib.qpu_client import (
    JobCancelationError,
    QPUClient,
    QPUClientRequestError,
    QPUJobInfo,
)
from warden.scheduler.errors import QPUDownError

logger = logging.getLogger(__name__)


class JobLogHandler(logging.Handler):
    def __init__(self, level=0):
        super().__init__(level)
        self.logs_records: list[str] = []

    def emit(self, record):
        try:
            msg = self.format(record)
            self.logs_records.append(msg)
        except Exception:
            self.handleError(record)

    def get_logs(self) -> str:
        return "\n".join(self.logs_records)


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
        self, queue: Queue, nb_run: int, sequence: str, batch_id: str | None = None
    ) -> None:
        """Wrap job execution to capture job execution logs and update those logs in the queue"""

        # User-visible logs should only be > INFO level
        job_log_handler = JobLogHandler(logging.INFO)
        logger.addHandler(job_log_handler)

        qpu_job_info = await self._execute_job(queue, nb_run, sequence, batch_id)

        # Update the job logs at the end of the job execution
        qpu_job_info = qpu_job_info.set_logs(job_log_handler.get_logs())
        await queue.put(qpu_job_info)

    async def _execute_job(
        self, queue: Queue, nb_run: int, sequence: str, batch_id: str | None = None
    ) -> QPUJobInfo:
        """Execute job on the QPU"""

        # Object to store job status and information to send to the db
        qpu_job = QPUJobInfo()

        qpu_job = await self.poll_qpu(queue=queue, qpu_job=qpu_job)
        if qpu_job.status == "ERROR":
            return qpu_job
        logger.info("QPU is operational")

        qpu_job = await self.create_job(
            queue=queue,
            qpu_job=qpu_job,
            nb_run=nb_run,
            sequence=sequence,
            batch_id=batch_id,
        )
        if qpu_job.status == "ERROR":
            return qpu_job
        logger.info("Job created on QPU")

        qpu_job = await self.await_job_execution(queue, qpu_job)
        if qpu_job.status not in ("CANCELED", "ERROR"):
            logger.info("Job execution done")
        return qpu_job

    async def poll_qpu(self, queue: Queue, qpu_job: QPUJobInfo) -> QPUJobInfo:
        """Check the QPU status"""
        try:
            polling_start = datetime.now()
            while not self.is_operational:
                if self.is_timed_out(
                    self.conf_sched.qpu_polling_timeout_s, polling_start
                ):
                    raise QPUDownError
                logger.info(
                    f"QPU not operational, will try again in {self.conf_sched.qpu_polling_interval_s}s"
                )
                await asyncio.sleep(self.conf_sched.qpu_polling_interval_s)
        except QPUDownError:
            logger.error(
                "QPU not operational for more than "
                f"{self.conf_sched.qpu_polling_timeout_s} seconds. Aborting. "
                "Submit when the QPU's status is 'UP'. "
            )
            qpu_job = qpu_job.to_error()
            await queue.put(qpu_job)
        except QPUClientRequestError as e:
            logger.error(f"Failed polling QPU status: {e}")
            qpu_job = qpu_job.to_error()
            await queue.put(qpu_job)
        return qpu_job

    async def create_job(
        self,
        queue: Queue,
        qpu_job: QPUJobInfo,
        nb_run: int,
        sequence: int,
        batch_id: str,
    ) -> QPUJobInfo:
        """Create the job on the QPU"""
        try:
            qpu_job = self.qpu_client.create_job(
                nb_run=nb_run,
                abstract_sequence=sequence,
                batch_id=batch_id,
            )
        except QPUClientRequestError as e:
            logger.error(f"Failed creating job: {e}")
            qpu_job = qpu_job.to_error()
            await queue.put(qpu_job)
        return qpu_job

    async def await_job_execution(
        self, queue: Queue, qpu_job: QPUJobInfo
    ) -> QPUJobInfo:
        """Polling the job status untill completion, error, or cancellation"""
        polling_start = datetime.now()
        qpu_job = self._get_job_poll(qpu_job)
        await queue.put(qpu_job)
        while qpu_job.status not in ["ERROR", "DONE", "CANCELED"]:
            if self.is_timed_out(self.conf_sched.job_polling_timeout_s, polling_start):
                logger.warning(
                    f"Job timed out (max {self.conf_sched.job_polling_timeout_s} s). "
                    "Terminating its associated QPU job "
                    f"{qpu_job.uid}."
                )
                try:
                    qpu_job = self.qpu_client.cancel_job(qpu_job)
                except (JobCancelationError, QPUClientRequestError) as e:
                    logger.error(f"Failed cancelling job: {e}")
                    qpu_job = qpu_job.to_error()
                    await queue.put(qpu_job)
                    continue
                logger.info("Job cancellation done")
                await queue.put(qpu_job)
                continue
            await asyncio.sleep(self.conf_sched.job_polling_interval_s)
            qpu_job = self._get_job_poll(qpu_job)
            await queue.put(qpu_job)
        return qpu_job

    def _get_job_poll(self, qpu_job: QPUJobInfo) -> QPUJobInfo:
        try:
            # When polling the job status, we set no_retry=True as we are
            # in the job polling loop that will handle the retry of the requests
            # until an eventual timout of the job
            qpu_job = self.qpu_client.get_job(qpu_job, no_retry=True)
            logger.info(f"Job status: {qpu_job.status}")
        except QPUClientRequestError as e:
            logger.warning(
                f"Got an error while polling job status: {e}."
                f"Continuing polling, last known job status: {qpu_job.status}."
            )
        return qpu_job
