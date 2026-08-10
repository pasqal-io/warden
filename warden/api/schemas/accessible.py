from pydantic import BaseModel


class AccessibleResponse(BaseModel):
    is_accessible: bool
    message: str
    qpu_slots_total: int | None = None
    qpu_slots_used: int | None = None
    qpu_slots_available: int | None = None


class UpdateAccessibleRequest(BaseModel):
    is_accessible: bool
    message: str = "Accessibility toggled"
