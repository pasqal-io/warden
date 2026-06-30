from dataclasses import dataclass


@dataclass
class TimedConfig:
    is_timed: bool
    shot_duration_s: float
