from pydantic import BaseModel


class AccessibleResponse(BaseModel):
    is_accessible: bool
    message: str


class UpdateAccessibleRequest(BaseModel):
    is_accessible: bool
    message: str = "Accessibility toggled"
