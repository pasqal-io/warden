from __future__ import annotations

from typing import cast

import numpy as np
import pulser
from pulser import ConstantWaveform, InterpolatedWaveform, Register
from pulser import Sequence as PulserSequence
from pulser.channels.base_channel import Channel
from pulser.devices import Device
from pulser.register import RegisterLayout
from pulser.waveforms import Waveform

from warden.api.schemas.jobs import AHSDrivingFields, AHSSequence, AHSTimeSeries


def _setup_register_and_layout(
    ahs_sequence: AHSSequence, device: Device
) -> PulserSequence:
    layout = ahs_sequence.setup.ahs_register.sites
    filling = ahs_sequence.setup.ahs_register.filling
    register_coords = [(x * 1e6, y * 1e6) for (x, y), f in zip(layout, filling) if f]

    register = Register.from_coordinates(register_coords, prefix="q")
    if device.requires_layout:
        reg_layout = RegisterLayout(
            [(coord[0] * 1e6, coord[1] * 1e6) for coord in layout]
        )
        trap_ids = reg_layout.get_traps_from_coordinates(*register_coords)
        reg_candidate = reg_layout.define_register(
            *trap_ids, qubit_ids=register.qubit_ids
        )

        try:
            device.validate_register(reg_candidate)
        except ValueError:
            reg_candidate = register.with_automatic_layout(device=device)

        register = reg_candidate

    seq = pulser.Sequence(register, device)
    seq.declare_channel("ising", "rydberg_global")
    return seq


def _waveform(series: AHSTimeSeries, duration: int, start: int, end: int) -> Waveform:
    """Return the samples `start` to `end` of an AHS series (rad/s) as a waveform in rad/us.

    The series is stretched to `duration` ns. AHS is linear between points; with a point
    1 ns from each side of every AHS point, Pulser's interpolation is linear except within
    1 ns of them.
    """
    points = np.array(series.times) / series.times[-1] * (duration - 1)
    knots = np.union1d(points, np.r_[points[:-1] + 1, points[1:] - 1])
    knots = np.r_[start, knots[(knots > start) & (knots < end - 1)], end - 1]
    values = np.interp(knots, points, series.values) / 1e6
    if np.all(values == values[0]):
        return cast(Waveform, ConstantWaveform(end - start, values[0]))
    times = (knots - start) / (end - start - 1)
    return cast(Waveform, InterpolatedWaveform(end - start, values, times))


def _phase_intervals(
    phase: AHSTimeSeries, duration: int, channel: Channel
) -> list[tuple[int, int, float]]:
    """Split `duration` ns into (start, end, phase) intervals of constant AHS phase.

    AHS holds the phase constant between time points. Each change moves to the nearest
    clock period of the stretched schedule, and a change closer than the channel's
    minimum pulse duration to the previous one (or to the end) moves with it.
    """
    clock, min_duration = channel.clock_period, channel.min_duration
    starts, phases = [0], [phase.values[0]]
    for t, value in zip(phase.times[1:-1], phase.values[1:-1]):
        start = clock * round(t / phase.times[-1] * duration / clock)
        if value == phases[-1]:
            continue
        if start - starts[-1] < min_duration:
            phases[-1] = value
        else:
            starts.append(start)
            phases.append(value)
    if len(starts) > 1 and duration - starts[-1] < min_duration:
        del starts[-1], phases[-1]
    return list(zip(starts, starts[1:] + [duration], phases))


def _validate_sequences(
    pulse: AHSDrivingFields,
) -> tuple[AHSTimeSeries, AHSTimeSeries, AHSTimeSeries, int]:
    fields = {
        "amplitude": pulse.amplitude,
        "detuning": pulse.detuning,
        "phase": pulse.phase,
    }
    for name, field in fields.items():
        if field.pattern != "uniform":
            raise NotImplementedError(
                f"pattern {field.pattern} not supported for {name}"
            )

    amp, det, phases = (field.time_series for field in fields.values())
    final_time = max(series.times[-1] for series in (amp, det, phases))
    if any(
        abs(series.times[0]) > 1e-9 or abs(series.times[-1] - final_time) > 1e-9
        for series in (amp, det, phases)
    ):
        raise ValueError(
            "Please ensure Hamiltonian is programmed for the full duration, from t=0 "
            "to the final time."
        )

    return amp, det, phases, int(round(final_time * 1e9))


def cudaq_sequence_to_pulser(sequence: AHSSequence, device: Device) -> PulserSequence:
    seq = _setup_register_and_layout(sequence, device)
    hamiltonian = sequence.hamiltonian

    if hamiltonian.localDetuning:
        raise NotImplementedError("Local detuning modulation not yet supported")
    if len(hamiltonian.drivingFields) != 1:
        raise ValueError("All pulses should be programmed using a single Hamiltonian")

    channel = seq.declared_channels["ising"]
    amp, det, phases, td = _validate_sequences(hamiltonian.drivingFields[0])
    # Round up to the clock period; the schedule is stretched to the new duration
    td = channel.validate_duration(td)
    for start, end, phase in _phase_intervals(phases, td, channel):
        amp_wf, det_wf = _waveform(amp, td, start, end), _waveform(det, td, start, end)
        seq.add(pulser.Pulse(amp_wf, det_wf, phase), "ising")
    return seq


def normalize_cudaq_sequence(sequence: AHSSequence, qpu_specs: str | None) -> str:
    """Normalize CUDA-Q input into a serialized Pulser abstract sequence."""

    if qpu_specs is None:
        raise ValueError("QPU specs are required for CUDA-Q sequence conversion")

    device = Device.from_abstract_repr(qpu_specs)
    return cudaq_sequence_to_pulser(sequence, device).to_abstract_repr()
