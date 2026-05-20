from warden.api.schemas.jobs import JobCreate
from warden.api.utils.cudaq import AHSSequence


def test_job_create_parse_AHSSequence(cudaq_sequence: str, serialized_sequence: str):
    """Testing that job create request correctly detects and parse when a sequence is a cudaq payload"""
    N_SHOTS = 100

    job_create = JobCreate(sequence=cudaq_sequence, shots=N_SHOTS)
    assert isinstance(job_create.sequence, AHSSequence)

    job_create = JobCreate(sequence=serialized_sequence, shots=N_SHOTS)
    assert isinstance(job_create.sequence, str)
