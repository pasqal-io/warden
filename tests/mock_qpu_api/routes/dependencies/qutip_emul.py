"""Dependecy for Qutip emulation configuration"""

import os
from typing import Annotated

from fastapi import Depends, FastAPI, Request


def init_qutip_emul(app: FastAPI) -> None:
    app.state.qutip_emul = os.environ.get("MOCK_QPU_API_EMUL", False)


def get_qutip_emul(request: Request) -> bool:
    """Get the API configuration for Qutip emulation capabilities."""
    return request.app.state.qutip_emul


QutipEmulDep = Annotated[bool, Depends(get_qutip_emul)]
