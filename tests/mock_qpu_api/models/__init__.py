from typing import Generic, TypeVar

from pydantic import BaseModel

from mock_qpu_api.models.jobs import Job
from mock_qpu_api.models.program import Program
from mock_qpu_api.models.system import QPU, QPUOperational

T = TypeVar("T")


class JSendResponse(BaseModel, Generic[T]):
    code: int
    message: str = "OK."
    data: T
    status: str = "success"


__all__ = ["Job", "Program", "QPU", "QPUOperational"]
