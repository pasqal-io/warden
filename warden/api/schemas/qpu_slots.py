from pydantic import BaseModel


class QPUSlotsResponse(BaseModel):
    qpu_slots_total: int
    qpu_slots_used: int
    qpu_slots_available: int
