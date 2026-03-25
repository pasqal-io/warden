"""QPU API client"""

import json
import logging
import uuid
from typing import Any

from httpx import AsyncClient, Client, Response

from .types import QPUJobInfo, QPUInfo, QPUOperationalStatus, QPUStatus

logger = logging.getLogger(__name__)

class QPUClient:
    """A client to communicate with the QPU's API.

    Args:
        base_uri: the IP address of the QPU.
        version: the version of its API.
    """

    def __init__(
        self,
        base_uri: str,
    ) -> None:
        self._base_uri = base_uri + "/api/v1"
        self.client = Client()

    @property
    def base_uri(self) -> str:
        """Base URI of the QPU (IP/version)."""
        return self._base_uri

    def get_operational_status(self) -> QPUStatus:
        """Gets QPU's operational status."""
        response = self._get("/system/operational")
        data = response.json()["data"]
        return QPUOperationalStatus(**data).operational_status

    def get_specs(self) -> Any | None:
        """Gets the Device implemented by the QPU."""
        response = self._get("/system")
        data = response.json()["data"]
        return QPUInfo(**data).specs

    def get_job(self, job: QPUJobInfo) -> QPUJobInfo:
        """Gets information on a submitted job."""
        response = self._get(f"/jobs/{job.uid}")
        data = response.json()["data"]
        return QPUJobInfo(**data)

    def get_program_status(self, program_id: int) -> str:
        """Gets the status of a program."""
        response = self._get(f"/programs/{program_id}")
        return json.dumps(response.json()["data"]["status"])

    def create_job(
        self, nb_run: int, abstract_sequence: str, batch_id: str | None = None
    ) -> QPUJobInfo:
        """Create job on the QPU to run an abstract Sequence nb_run times."""
        # By default, submitting a job to the QPU cancels the previous job submitted
        pasqman_job_id = f"{uuid.uuid4()}"
        if batch_id is None:
            batch_id = f"pasqal-local-batch-{pasqman_job_id}"
        logger.debug(f"Creating pasqman_job_id {pasqman_job_id} for batch id {batch_id}")
        payload = {
            "nb_run": nb_run,
            "pulser_sequence": abstract_sequence,
            "context": {"batch_id": batch_id, "pasqman_job_id": pasqman_job_id},
        }
        response = self._post("/jobs", payload)
        data = response.json()["data"]
        return QPUJobInfo(**data)

    def cancel_job(self, job_info: QPUJobInfo) -> QPUJobInfo:
        """Terminates the execution of a given job ID."""
        program_id = job_info.program_id
        program_status = self.get_program_status(program_id)

        if program_status not in [
            '"ABORTED"',
            '"ABORTING"',
            '"ERROR"',
            '"MISSING_CALIBRATION"',
            '"DONE"',
            '"INVALID"',
        ]:
            response = self._put(f"/jobs/{job_info.uid}/cancel")
            data = response.json()["data"]
            return QPUJobInfo(**data)
        else:
            logger.error(f"Job {job_info.id} already terminated, cannot cancel")
            return self.get_job(job_info.id)

    def _get(self, suffix: str) -> Response:
        """Sends a GET request to base_uri + suffix.

        Arg:
            suffix: The suffix to add after base_uri for the request.

        Returns:
            The Response returned by the GET request.
        """
        response = self.client.get(self.base_uri + suffix)
        response.raise_for_status()
        return response

    def _post(self, suffix: str, data: dict | None = None) -> Response:
        """Sends a POST request to base_uri + suffix.

        Arg:
            suffix: The suffix to add after base_uri for the request.
            data: The data to POST, as a JSON dictionnary.

        Returns:
            The Response returned by the POST request.
        """
        response = self.client.post(self.base_uri + suffix, json=data)
        response.raise_for_status()
        return response

    def _delete(self, suffix: str) -> Response:
        """Sends a DELETE request to base_uri + suffix.

        Arg:
            suffix: The suffix to add after base_uri for the request.

        Returns:
            The Response returned by the DELETE request.
        """
        response = self.client.delete(self.base_uri + suffix)
        response.raise_for_status()
        return response

    def _put(self, suffix: str, data: dict | None = None) -> Response:
        """Sends a PUT request to base_uri + suffix.

        Arg:
            suffix: The suffix to add after base_uri for the request.
            data:  The data to PUT, as a JSON dictionnary.

        Returns:
            The Response returned by the DELETE request.
        """
        response = self.client.put(self.base_uri + suffix, json=data)
        response.raise_for_status()
        return response


class AsyncQPUClient:
    """HTTP Client to interact with the pasqos API."""

    def __init__(self, uri):
        self.uri = uri
        self.client = AsyncClient()

    async def get_specs(self) -> str:
        """Get QPU serialized device specs."""
        response = await self.client.get(f"{self.uri}/api/v1/system")
        response.raise_for_status()
        return json.dumps(response.json()["data"]["specs"])
