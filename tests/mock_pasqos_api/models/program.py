from enum import Enum

from pydantic import BaseModel


class ProgramStatus(Enum):
    """The list of the possible program status.

    CREATED: The program has been created
    WAITING: The program is waiting for the QPU
    COMPILING: The program is being compiled
    RUNNING: The program is being run on the QPU
    INVALID: The program format is invalid
    ERROR: The program is stopped because an error occurred
    DONE: The program ended successfully
    ABORTING: The program is requested to abort
    ABORTED: The program was aborted by user
    PAUSED: The program execution is paused
    CANCELED: The program has been canceled while it was in queue / not started yet
    UNEXPECTED_END: The program ended unexpectedly
    PENDING_CALIBRATION: The program is waiting needed calibration programs
    MISSING_CALIBRATION: The program ended with error because of missing calibration
    BAD_PARAMETERS: The program ended with error because of bad parameters
    UNKNOWN_PROCEDURE The program ended with error because of an unknown procedure
    OUT_OF_SPECS: The program definition is out of QPU specification
    """

    CREATED = "CREATED"
    WAITING = "WAITING"
    COMPILING = "COMPILING"
    RUNNING = "RUNNING"
    INVALID = "INVALID"
    ERROR = "ERROR"
    DONE = "DONE"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"
    PAUSED = "PAUSED"
    CANCELED = "CANCELED"
    UNEXPECTED_END = "UNEXPECTED_END"
    PENDING_CALIBRATION = "PENDING_CALIBRATION"
    MISSING_CALIBRATION = "MISSING_CALIBRATION"
    BAD_PARAMETERS = "BAD_PARAMETERS"
    UNKNOWN_PROCEDURE = "UNKNOWN_PROCEDURE"
    OUT_OF_SPECS = "OUT_OF_SPECS"


class Program(BaseModel):
    # Only thing that interests us here
    uid: int
    status: ProgramStatus
