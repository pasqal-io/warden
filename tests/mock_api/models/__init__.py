from typing import Generic, TypeVar

from pydantic import BaseModel

from .jobs import Job
from .program import Program
from .system import QPU, QPUOperational

T = TypeVar("T")


class StandardResponse(BaseModel, Generic[T]):
    code: int
    message: str
    data: T
    status: str = "OK"


__all__ = ["Job", "Program", "QPU", "QPUOperational"]
