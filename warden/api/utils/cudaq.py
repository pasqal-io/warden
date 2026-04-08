from __future__ import annotations

import pulser
from pulser import CustomWaveform, InterpolatedWaveform, Register
from pulser import Sequence as PulserSequence
from pulser.devices import Device
from pulser.math.abstract_array import AbstractArray
from pulser.register import RegisterLayout
from pulser.waveforms import ConstantWaveform, Waveform

from warden.api.schemas.jobs import AHSDrivingFields, AHSSequence, AHSTimeSeries


def _setup_register_and_layout(
    ahs_sequence: AHSSequence, device: Device
) -> PulserSequence:
    layout = ahs_sequence.setup.ahs_register.sites
    filling = ahs_sequence.setup.ahs_register.filling
    register_coords: list[tuple[float, float]] = []
    for i, coord in enumerate(layout):
        if filling[i]:
            register_coords.append((coord[0] * 1e6, coord[1] * 1e6))

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


def _timeseries_to_waveform(
    series: AHSTimeSeries, duration: int, scale: float, sign: float = 1.0
) -> Waveform:
    values = [sign * v / scale for v in series.values]
    if all(abs(v - values[0]) <= 1e-12 for v in values):
        return ConstantWaveform(duration, values[0])

    return InterpolatedWaveform(
        duration,
        values=values,
        times=[t * 1e9 / duration for t in series.times],
        interpolator="interp1d",
    )


def _setup_amplitude_and_detuning(
    amp: AHSTimeSeries, det: AHSTimeSeries, td: int
) -> tuple[CustomWaveform, Waveform]:
    amp_wf = CustomWaveform(_timeseries_to_waveform(amp, td, 1e6).samples)
    det_wf = _timeseries_to_waveform(det, td, 1e6)
    return amp_wf, det_wf


def _setup_phase(
    phases: AHSTimeSeries,
    amp_wf: CustomWaveform,
    det_wf: Waveform,
    td: int,
) -> tuple[CustomWaveform, AbstractArray]:
    phase_wf = CustomWaveform(
        _timeseries_to_waveform(phases, td, 1e6, sign=-1.0).samples
    )
    phase_mod = pulser.Pulse.ArbitraryPhase(amp_wf, phase_wf)
    full_det_wf = CustomWaveform(det_wf.samples + phase_mod.detuning.samples)
    return full_det_wf, phase_mod.phase


def _validate_sequences(
    pulse: AHSDrivingFields,
) -> tuple[AHSTimeSeries, AHSTimeSeries, AHSTimeSeries, int]:
    if pulse.amplitude.pattern != "uniform":
        raise NotImplementedError(
            f"pattern {pulse.amplitude.pattern} not supported for amplitude"
        )
    if pulse.detuning.pattern != "uniform":
        raise NotImplementedError(
            f"pattern {pulse.detuning.pattern} not supported for detuning"
        )
    if pulse.phase.pattern != "uniform":
        raise NotImplementedError(
            f"pattern {pulse.phase.pattern} not supported for phase"
        )

    amp = pulse.amplitude.time_series
    det = pulse.detuning.time_series
    phases = pulse.phase.time_series
    final_time = max(amp.times[-1], det.times[-1], phases.times[-1])
    total_duration = int(round(final_time * 1e9))

    if (
        abs(amp.times[0]) > 1e-9
        or abs(det.times[0]) > 1e-9
        or abs(phases.times[0]) > 1e-9
        or abs(amp.times[-1] - final_time) > 1e-9
        or abs(det.times[-1] - final_time) > 1e-9
        or abs(phases.times[-1] - final_time) > 1e-9
    ):
        raise ValueError(
            "Please ensure Hamiltonian is programmed for the full duration, from t=0 "
            "to the final time."
        )

    return amp, det, phases, total_duration


def cudaq_sequence_to_pulser(sequence: AHSSequence, device: Device) -> PulserSequence:
    seq = _setup_register_and_layout(sequence, device)
    hamiltonian = sequence.hamiltonian

    if hamiltonian.localDetuning:
        raise NotImplementedError("Local detuning modulation not yet supported")
    if len(hamiltonian.drivingFields) != 1:
        raise ValueError("All pulses should be programmed using a single Hamiltonian")

    for pulse in hamiltonian.drivingFields:
        amp, det, phases, td = _validate_sequences(pulse)
        amp_wf, det_wf = _setup_amplitude_and_detuning(amp, det, td)
        full_det_wf, phase = _setup_phase(phases, amp_wf, det_wf, td)
        seq.add(pulser.Pulse(amp_wf, full_det_wf, phase), "ising")
    return seq


def normalize_job_sequence(sequence: str | AHSSequence, qpu_specs: str | None) -> str:
    """Normalize Pulser/CUDA-Q input into a serialized Pulser abstract sequence."""
    if isinstance(sequence, str):
        return sequence

    if qpu_specs is None:
        raise ValueError("QPU specs are required for CUDA-Q sequence conversion")

    device = Device.from_abstract_repr(qpu_specs)
    return cudaq_sequence_to_pulser(sequence, device).to_abstract_repr()
