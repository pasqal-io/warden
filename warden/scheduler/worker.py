"""Worker to send jobs to QPU"""

import logging
import asyncio
from asyncio import Queue
from datetime import datetime

from warden.lib.config import Config
from warden.lib.qpu_client import QPUClient, QPUJobInfo

from warden.scheduler.errors import QPUDownError

logger = logging.getLogger(__name__)


class LocalQPUWorker:
    """Local Pasqal QPU Worker"""

    def __init__(self, conf: Config):
        self.conf = conf
        self.client = QPUClient(base_uri=conf.qpu.uri)
        self.previous_job_status: QPUJobInfo | None = None

    @property
    def operational_status(self):
        return self.client.get_operational_status()

    @property
    def is_operational(self):
        return self.operational_status == "UP"

    @staticmethod
    def is_timed_out(timeout_s: int | float, start: datetime) -> bool:
        if timeout_s < 0:
            return False
        return (datetime.now() - start).total_seconds() > timeout_s

    async def _poll_qpu_status(self) -> None:
        """Polls QPU until it is operational."""
        polling_start = datetime.now()
        while not self.is_operational:
            if self.is_timed_out(
                self.conf.scheduler.qpu_polling_timeout_s, polling_start
            ):
                raise QPUDownError
            logger.info(
                f"QPU not operational, will try again in {self.conf.scheduler.qpu_polling_interval_s}s"
            )
            await asyncio.sleep(self.conf.scheduler.qpu_polling_interval_s)

    async def _get_job_and_queue(self, queue: Queue[QPUJobInfo], qpu_job: QPUJobInfo) -> QPUJobInfo:
        """Get job info and if update, send to db commit"""
        qpu_job = self.client.get_job(qpu_job)
        logger.info(f"Job status: {qpu_job.status}")
        if qpu_job != self.previous_job_status:
            await queue.put(qpu_job)
            self.previous_job_status = qpu_job
        return qpu_job

    async def execute_job(
        self, queue: asyncio.Queue, nb_run: int, sequence, batch_id=None
    ) -> None:
        """Submit job to run on the QPU"""
        self.previous_job_status = None

        try:
            await self._poll_qpu_status()
        except QPUDownError:
            logger.error(
                "QPU not operational for more than "
                f"{self.conf.scheduler.qpu_polling_timeout_s} seconds. Aborting. "
                "Submit when the QPU's status is 'UP'. "
            )
            await queue.put(QPUJobInfo(status="ERROR"))
            return
        logger.info("QPU is operational.")

        qpu_job = self.client.create_job(
            nb_run=nb_run,
            abstract_sequence=sequence,
            batch_id=batch_id,
        )

        polling_start = datetime.now()
        qpu_job = await self._get_job_and_queue(queue, qpu_job)
        while qpu_job.status not in ["ERROR", "DONE", "CANCELED"]:
            await asyncio.sleep(self.conf.scheduler.job_polling_interval_s)
            if self.is_timed_out(
                self.conf.scheduler.job_polling_timeout_s, polling_start
            ):
                logger.warning(
                    f"Job timed out (max {self.conf.scheduler.job_polling_timeout_s} s). "
                    "Terminating its associated QPU job "
                    f"{qpu_job.uid}."
                )
                self.client.cancel_job(qpu_job)
                qpu_job = await self._get_job_and_queue(queue, qpu_job)
                # TODO: remove last poll and return immediatly with a CANCELED state ?
                logger.info("Job cancelled")
                break
            qpu_job = await self._get_job_and_queue(queue, qpu_job)
