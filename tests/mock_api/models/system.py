from typing import Any, Literal

from pydantic import BaseModel

class QPU(BaseModel):

    # Only thing we need for now 
    specs: dict[str, Any]

class QPUOperational(BaseModel):

    operational_status: Literal["UP", "DOWN"]