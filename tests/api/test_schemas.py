from warden.api.schemas.jobs import try_parse_AHSSequence
from warden.api.utils.cudaq import AHSSequence


def test_try_parse_AHSSequence(cudaq_sequence: str, serialized_sequence: str):
    """Testing that we are able to parse CUDA-Q sequences correctly"""

    sequence = try_parse_AHSSequence(sequence=cudaq_sequence)
    assert isinstance(sequence, AHSSequence)

    sequence = try_parse_AHSSequence(sequence=serialized_sequence)
    assert isinstance(sequence, str)
