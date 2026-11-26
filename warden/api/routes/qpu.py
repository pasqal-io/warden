from logging import getLogger

from fastapi import APIRouter, HTTPException

from warden.api.routes.dependencies.qpu_client import APIQPUClient
from warden.api.schemas.qpu import QPUSpecsResponse
from warden.lib.qpu_client import QPUClientRequestError

logger = getLogger(__name__)
router = APIRouter(prefix="/qpu")


@router.get("/specs")
async def get_specs(
    client: APIQPUClient,
) -> QPUSpecsResponse:
    """Retrieve the serialized Pulser device specs of the QPU.

    The device specs define the hardware constraints of the QPU and can be loaded in to a
    Pulser `Device` object, see Pulser
    [docs](https://docs.pasqal.com/pulser/apidoc/_autosummary/pulser.devices.Device/#pulser.devices.Device.from_abstract_repr).

    With the `Device` object, one can create a Pulser `Sequence` which defines the
    pulses to be executed on the QPU.
    """
    try:
        return QPUSpecsResponse(specs=await client.get_specs())
    except QPUClientRequestError as e:
        raise HTTPException(503, detail=f"Failed getting device specs: {e}")
