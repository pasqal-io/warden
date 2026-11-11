import json

import pytest
from pulser.devices import Device

from warden.api.schemas.jobs import AHSSequence
from warden.api.utils.cudaq import cudaq_sequence_to_pulser


@pytest.fixture
def device(qpu_specs: dict) -> Device:
    return Device.from_abstract_repr(json.dumps(qpu_specs))


def _ahs_sequence(cudaq_sequence: str, **series) -> AHSSequence:
    sequence = json.loads(cudaq_sequence)
    for name, (times, values) in series.items():
        field = sequence["hamiltonian"]["drivingFields"][0][name]
        field["time_series"] = {"values": values, "times": times}
    return AHSSequence.model_validate(sequence)


@pytest.mark.parametrize(
    "times, values, expected",
    [
        ([0.0, 3e-7, 7.1e-7], [0.0, 0.5, 0.9], [(300, 0.0), (410, 0.5)]),
        ([0.0, 7.1e-7], [0.7, 0.7], [(710, 0.7)]),
    ],
)
def test_cudaq_phase_is_held_between_time_points(
    cudaq_sequence: str, device: Device, times, values, expected
):
    """Assert that each CUDA-Q phase interval becomes a pulse with that phase."""
    constant = (times, [1e6] * len(times))
    ahs = _ahs_sequence(
        cudaq_sequence, amplitude=constant, detuning=constant, phase=(times, values)
    )

    seq = cudaq_sequence_to_pulser(ahs, device)

    operations = json.loads(seq.to_abstract_repr())["operations"]
    assert [(op["amplitude"]["duration"], op["phase"]) for op in operations] == expected


@pytest.mark.parametrize("times", [[0.0, 1e-8, 2e-8, 7.1e-7], [0.0, 7e-7, 7.1e-7]])
def test_cudaq_rejects_intervals_shorter_than_min_duration(
    cudaq_sequence: str, device: Device, times
):
    """Assert that CUDA-Q time points closer than 16 ns are rejected."""
    series = (times, [0.0] * len(times))
    ahs = _ahs_sequence(cudaq_sequence, amplitude=series, detuning=series, phase=series)

    with pytest.raises(ValueError, match="at least 16 ns"):
        cudaq_sequence_to_pulser(ahs, device)


@pytest.mark.parametrize(
    "times, durations",
    [
        ([0.0, 1.6e-8, 3.2e-8, 7.1e-7], [16, 16, 678]),
        ([0.0, 2e-8, 4e-8, 7.1e-7], [20, 20, 670]),
        ([0.0, 6.94e-7, 7.1e-7], [694, 16]),
        ([0.0, 6.9e-7, 7.1e-7], [690, 20]),
    ],
)
def test_cudaq_accepts_intervals_of_at_least_min_duration(
    cudaq_sequence: str, device: Device, times, durations
):
    """Assert that CUDA-Q time points 16 ns or more apart each become a pulse."""
    series = (times, [0.0] * len(times))
    ahs = _ahs_sequence(cudaq_sequence, amplitude=series, detuning=series, phase=series)

    seq = cudaq_sequence_to_pulser(ahs, device)

    operations = json.loads(seq.to_abstract_repr())["operations"]
    assert [op["amplitude"]["duration"] for op in operations] == durations


def test_cudaq_fields_become_ramps_on_the_union_of_time_points(
    cudaq_sequence: str, device: Device
):
    """Assert that CUDA-Q amplitude and detuning become ramps between the union of time points."""
    ahs = _ahs_sequence(
        cudaq_sequence,
        amplitude=([0.0, 2.1e-7, 5e-7, 7.1e-7], [0.0, 9e6, 9e6, 5e6]),
        detuning=([0.0, 3e-7, 7.1e-7], [-9e6, 0.0, 8.2e6]),
        phase=([0.0, 7.1e-7], [0.0, 0.0]),
    )

    seq = cudaq_sequence_to_pulser(ahs, device)

    def ramp(wf: dict) -> tuple:
        if wf["kind"] == "constant":
            return wf["duration"], wf["value"], wf["value"]
        assert wf["kind"] == "ramp"
        return wf["duration"], wf["start"], wf["stop"]

    operations = json.loads(seq.to_abstract_repr())["operations"]
    assert [ramp(op["amplitude"]) for op in operations] == [
        (210, 0.0, 9.0),
        (90, 9.0, 9.0),
        (200, 9.0, 9.0),
        (210, 9.0, 5.0),
    ]
    assert [ramp(op["detuning"]) for op in operations] == [
        (210, -9.0, -2.7),
        (90, -2.7, 0.0),
        (200, 0.0, 4.0),
        (210, 4.0, 8.2),
    ]
