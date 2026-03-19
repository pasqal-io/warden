from fastapi import APIRouter, Depends
from warden.api.dependencies.qpu_client import get_qpu_client
from warden.qpu_client import QPUClient
from logging import getLogger

from warden.schemas.qpu import QPUSpecsResponse

logger = getLogger(__name__)
router = APIRouter(prefix="/qpu")


@router.get("/specs")
async def get_specs(
    client: QPUClient = Depends(get_qpu_client),
) -> QPUSpecsResponse:
    """Retrieve the serialized Pulser device specs of the QPU.

    The device specs define the hardware constraints of the QPU and can be loaded in to a
    Pulser `Device` object, see Pulser
    [docs](https://docs.pasqal.com/pulser/apidoc/_autosummary/pulser.devices.Device/#pulser.devices.Device.from_abstract_repr).

    With the `Device` object, one can create a Pulser `Sequence` which defines the
    pulses to be executed on the QPU.
    """
    return QPUSpecsResponse(specs=await client.get_specs())
