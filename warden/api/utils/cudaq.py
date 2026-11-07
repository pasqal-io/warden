from __future__ import annotations

from typing import cast

import numpy as np
import pulser
from pulser import ConstantWaveform, RampWaveform, Register
from pulser import Sequence as PulserSequence
from pulser.devices import Device
from pulser.register import RegisterLayout
from pulser.waveforms import Waveform

from warden.api.schemas.jobs import AHSDrivingFields, AHSSequence


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


def _ramp(duration: int, start: float, stop: float) -> Waveform:
    if start == stop:
        return cast(Waveform, ConstantWaveform(duration, start))
    return cast(Waveform, RampWaveform(duration, start, stop))


def _validate_sequences(
    pulse: AHSDrivingFields,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return the union of the AHS time points (ns) and the fields at each of them.

    Amplitude and detuning (rad/us) are linear between their own points; the phase is
    held from each of its points to the next.
    """
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

    amp, det, phase = (
        (np.round(np.array(field.time_series.times) * 1e9), field.time_series.values)
        for field in fields.values()
    )
    final_time = max(series[0][-1] for series in (amp, det, phase))
    if any(t[0] != 0 or t[-1] != final_time for t, _ in (amp, det, phase)):
        raise ValueError(
            "Please ensure Hamiltonian is programmed for the full duration, from t=0 "
            "to the final time."
        )

    times = np.unique(np.concatenate([amp[0], det[0], phase[0]]))
    phase_values = np.array(phase[1])[np.searchsorted(phase[0], times, "right") - 1]
    return (
        times,
        np.interp(times, *amp) / 1e6,
        np.interp(times, *det) / 1e6,
        phase_values,
    )


def cudaq_sequence_to_pulser(sequence: AHSSequence, device: Device) -> PulserSequence:
    seq = _setup_register_and_layout(sequence, device)
    hamiltonian = sequence.hamiltonian

    if hamiltonian.localDetuning:
        raise NotImplementedError("Local detuning modulation not yet supported")
    if len(hamiltonian.drivingFields) != 1:
        raise ValueError("All pulses should be programmed using a single Hamiltonian")

    times, amp, det, phase = _validate_sequences(hamiltonian.drivingFields[0])
    # One pulse per pair of time points; Pulser rounds each duration up to the clock
    # period (with a warning) and rejects pulses shorter than the channel minimum
    for i, duration in enumerate(np.diff(times).astype(int)):
        seq.add(
            pulser.Pulse(
                _ramp(duration, amp[i], amp[i + 1]),
                _ramp(duration, det[i], det[i + 1]),
                phase[i],
            ),
            "ising",
        )
    return seq


def normalize_cudaq_sequence(sequence: AHSSequence, qpu_specs: str | None) -> str:
    """Normalize CUDA-Q input into a serialized Pulser abstract sequence."""

    if qpu_specs is None:
        raise ValueError("QPU specs are required for CUDA-Q sequence conversion")

    device = Device.from_abstract_repr(qpu_specs)
    return cudaq_sequence_to_pulser(sequence, device).to_abstract_repr()
