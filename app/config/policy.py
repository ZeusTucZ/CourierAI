from typing import Literal

from app.models.common import Model, Positive


class PolicyConfig(Model):
    # Official safety limits; literals prevent accidental relaxation by a snapshot.
    night_start_hour: Literal[22] = 22
    mandatory_riding_limit_min: Literal[240] = 240
    mandatory_break_min: Literal[20] = 20
    heat_start_hour: Literal[12] = 12
    heat_end_hour: Literal[16] = 16
    heat_riding_limit_min: Literal[90] = 90
    # MVP assumptions, not official thresholds. Calibrate later.
    default_shift_hours: Positive = 8
    minimum_service_time_min: Positive = 1
