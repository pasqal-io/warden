"""QPU API client"""

import json
import logging
import uuid

from httpx import AsyncClient, Response

from warden.lib.config.config import QPUConfig
from warden.lib.qpu_client.retry import NotRetriedHTTPStatus, retry
from warden.lib.qpu_client.types import (
    QPUInfo,
    QPUJobInfo,
    QPUOperationalStatus,
    QPUStatus,
)

logger = logging.getLogger(__name__)


class JobCancelationError(Exception):
    pass


class HTTPClientWrapper:
    """HTTP client wrapper for exception handling"""

    def __init__(
        self,
        qpu_conf: QPUConfig,
    ):
        self.client = qpu_conf.client
        self.retry_max = qpu_conf.retry_max
        self.retry_sleep_s = qpu_conf.retry_sleep_s

    def get(self, suffix: str, no_retry: bool = False) -> Response:
        """Sends a GET request to base_url + suffix.

        Arg:
            suffix: The suffix to add after base_url for the request.
            no_retry: Do not attempt to retry request

        Returns:
            The Response returned by the GET request.
        """
        response = retry(
            max=self.retry_max, sleep_s=self.retry_sleep_s, no_retry=no_retry
        )(self._get)(suffix)
        return response

    def post(
        self, suffix: str, json: dict | None = None, no_retry: bool = False
    ) -> Response:
        """Sends a POST request to base_url + suffix.

        Arg:
            suffix: The suffix to add after base_url for the request.
            json: The data to POST, as a JSON dictionnary.
            no_retry: Do not attempt to retry request

        Returns:
            The Response returned by the POST request.
        """
        response = retry(
            max=self.retry_max, sleep_s=self.retry_sleep_s, no_retry=no_retry
        )(self._post)(suffix, json)
        return response

    def delete(self, suffix: str, no_retry: bool = False) -> Response:
        """Sends a DELETE request to base_url + suffix.

        Arg:
            suffix: The suffix to add after base_url for the request.
            no_retry: Do not attempt to retry request

        Returns:
            The Response returned by the DELETE request.
        """
        response = retry(
            max=self.retry_max, sleep_s=self.retry_sleep_s, no_retry=no_retry
        )(self._delete)(suffix)
        return response

    def put(
        self, suffix: str, json: dict | None = None, no_retry: bool = False
    ) -> Response:
        """Sends a PUT request to base_url + suffix.

        Arg:
            suffix: The suffix to add after base_url for the request.
            json:  The data to PUT, as a JSON dictionnary.
            no_retry: Do not attempt to retry request

        Returns:
            The Response returned by the DELETE request.
        """
        response = retry(
            max=self.retry_max, sleep_s=self.retry_sleep_s, no_retry=no_retry
        )(self._put)(suffix, json)
        return response

    def _get(self, suffix: str) -> Response:
        response = self.client.get(suffix)
        response.raise_for_status()
        return response

    def _post(self, suffix: str, json: dict | None = None) -> Response:
        response = self.client.post(suffix, json=json)
        response.raise_for_status()
        return response

    def _delete(self, suffix: str) -> Response:
        response = self.client.delete(suffix)
        response.raise_for_status()
        return response

    def _put(self, suffix: str, json: dict | None = None) -> Response:
        response = self.client.put(suffix, json=json)
        response.raise_for_status()
        return response


class QPUClient:
    """QPU client

    Args:
        qpu_conf: QPUConfig object
    """

    def __init__(self, qpu_conf: QPUConfig) -> None:
        self.client = HTTPClientWrapper(qpu_conf)

    def get_operational_status(self) -> QPUStatus:
        """Gets QPU's operational status."""
        response = self.client.get("/system/operational")
        data = response.json()["data"]
        status = QPUOperationalStatus(**data).operational_status
        if status is None:
            raise ValueError(
                "QPU operational status response is missing 'operational_status'"
            )
        return status

    def get_job(self, job_uid: int, no_retry: bool = False) -> QPUJobInfo:
        """Gets information on a submitted job."""
        response = self.client.get(f"/jobs/{job_uid}", no_retry)
        data = response.json()["data"]
        return QPUJobInfo(**data)

    def create_job(
        self, nb_run: int, abstract_sequence: str, batch_id: str | None = None
    ) -> QPUJobInfo:
        """Create job on the QPU to run an abstract Sequence nb_run times."""
        # By default, submitting a job to the QPU cancels the previous job submitted
        pasqman_job_id = f"{uuid.uuid4()}"
        if batch_id is None:
            batch_id = f"pasqal-local-batch-{pasqman_job_id}"
        logger.debug(
            f"Creating pasqman_job_id {pasqman_job_id} for batch id {batch_id}"
        )
        payload = {
            "nb_run": nb_run,
            "pulser_sequence": abstract_sequence,
            "context": {"batch_id": batch_id, "pasqman_job_id": pasqman_job_id},
        }
        response = self.client.post("/jobs", payload)
        data = response.json()["data"]
        return QPUJobInfo(**data)

    def cancel_job(self, job_uid: int) -> QPUJobInfo:
        """Terminates the execution of a given job ID."""
        try:
            response = self.client.put(f"/jobs/{job_uid}/cancel")
            data = response.json()["data"]
            return QPUJobInfo(**data)
        except NotRetriedHTTPStatus as e:
            resp = e.response
            if resp.status_code != 400:
                raise JobCancelationError(e) from e
            ret_code = resp.json()["code"]
            data = resp.json()["data"]
            cant_cancel_job_code = "3003"
            if cant_cancel_job_code not in ret_code:
                raise JobCancelationError(e) from e
            # Can't cancel job because associated program can't be aborted | canceled
            # That probably means that our job information is outdated so we fetch it again
            # and return
            logger.warning(
                f"Job can't be cancelled, program is in '{data['status']}' state."
            )
            job_info = self.get_job(job_uid)
            return job_info


class AsyncQPUClient:
    """HTTP Client to interact with the QPU API."""

    def __init__(self, qpu_conf: QPUConfig):
        self.conf = qpu_conf
        self.client = AsyncClient(base_url=qpu_conf.uri + "/api/v1")

    async def get_specs(self) -> str:
        """Get QPU serialized device specs."""
        response = await self.get("/system")
        data = response.json()["data"]
        return json.dumps(QPUInfo(**data).specs)

    async def get(self, suffix: str):
        """Sends a GET request to base_url + suffix.

        Arg:
            suffix: The suffix to add after base_url for the request.

        Returns:
            The Response returned by the GET request.
        """
        response = await retry(
            max=self.conf.retry_max, sleep_s=self.conf.retry_sleep_s
        )(self._get)(suffix)
        return response

    async def _get(self, suffix: str):
        response = await self.client.get(suffix)
        response.raise_for_status()
        return response
