from enum import Enum

from pydantic import BaseModel


class ProgramStatus(Enum):
    """The list of the possible program status.

    CREATED: The program has been created
    RUNNING: The program is being run on the QPU
    DONE: The program ended successfully
    CANCELED: The program has been canceled while it was in queue / not started yet
    """

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    CANCELED = "CANCELED"


class Program(BaseModel):
    # Only thing that interests us here
    uid: int
    status: ProgramStatus
