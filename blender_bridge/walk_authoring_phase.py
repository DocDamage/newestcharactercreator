"""First-party analytic targets for the original in-place walk.

All distances describe analytic ankle targets. Skin contact must be measured
independently. Positive forward is the rig's anatomical forward projected
onto the world floor. Stance width stays at the measured neutral width.
"""

from dataclasses import dataclass


FPS = 30
STORED_FRAMES = 300
STRIDE_FRAMES = 30
STANCE_FRAMES = 18
SWING_FRAMES = STRIDE_FRAMES - STANCE_FRAMES
RIGHT_LEAD_FRAMES = STRIDE_FRAMES // 2
GROUND_SPEED_M_S = 0.650
PEAK_ANKLE_LIFT_M = 0.050
ARMATURE_WORLD_Z_M = -0.045


@dataclass(frozen=True)
class FootSample:
    """Targets relative to this foot's neutral ankle in the rig's ground axes.

    The stance anchor adds unwrapped nominal travel to the forward offset.
    During swing it remains the preceding stance's anchor until the next
    cycle begins. Ankle lift is along world +Z.
    """

    phase_index: int
    is_stance: bool
    stance_anchor_m: float
    forward_m: float
    lift_m: float
    forward_velocity_m_s: float
    lift_velocity_m_s: float
    forward_acceleration_m_s2: float
    lift_acceleration_m_s2: float


@dataclass(frozen=True)
class WalkFrame:
    """One stored sample or the virtual sample at index 300."""

    index: int
    time_s: float
    armature_world_z_m: float
    left: FootSample
    right: FootSample


def _swing(u: float) -> tuple[float, float, float, float, float, float]:
    """Return normalized forward recovery and lift with two u derivatives."""
    remainder = 1.0 - u
    product = u * remainder
    direction = 1.0 - 2.0 * u

    recovery = u**3 * (10.0 + u * (-15.0 + 6.0 * u))
    recovery_d1 = 30.0 * product**2
    recovery_d2 = 60.0 * product * direction
    lift = 64.0 * product**3
    lift_d1 = 192.0 * product**2 * direction
    lift_d2 = 384.0 * product * (direction**2 - product)
    return recovery, recovery_d1, recovery_d2, lift, lift_d1, lift_d2


def _sample_foot(index: int, lead: int) -> FootSample:
    stride_index, phase_index = divmod(index + lead, STRIDE_FRAMES)
    phase_s = phase_index / FPS
    half_stance_s = STANCE_FRAMES / (2 * FPS)
    stride_s = STRIDE_FRAMES / FPS
    anchor_m = GROUND_SPEED_M_S * (
        (stride_index * STRIDE_FRAMES - lead) / FPS + half_stance_s
    )
    baseline_m = GROUND_SPEED_M_S * (half_stance_s - phase_s)
    if phase_index < STANCE_FRAMES:
        return FootSample(
            phase_index, True, anchor_m, baseline_m, 0.0,
            -GROUND_SPEED_M_S, 0.0, 0.0, 0.0,
        )

    swing_s = SWING_FRAMES / FPS
    u = (phase_index - STANCE_FRAMES) / SWING_FRAMES
    recovery, recovery_d1, recovery_d2, lift, lift_d1, lift_d2 = _swing(u)
    recovery_m = GROUND_SPEED_M_S * stride_s
    return FootSample(
        phase_index, False, anchor_m, baseline_m + recovery_m * recovery,
        PEAK_ANKLE_LIFT_M * lift,
        -GROUND_SPEED_M_S + recovery_m * recovery_d1 / swing_s,
        PEAK_ANKLE_LIFT_M * lift_d1 / swing_s,
        recovery_m * recovery_d2 / swing_s**2,
        PEAK_ANKLE_LIFT_M * lift_d2 / swing_s**2,
    )


def sample_walk(index: int) -> WalkFrame:
    """Sample the fixed profile at zero-based sample index 0 through 300.

    Indices 0..299 are stored. Index 300 repeats the rig-space targets and
    their derivatives exactly while the unwrapped stance anchors advance.
    The armature Z value is a fixed offset from its neutral world matrix.
    """
    if type(index) is not int or not 0 <= index <= STORED_FRAMES:
        raise ValueError("Walk sample index must be an integer from 0 through 300")
    return WalkFrame(
        index, index / FPS, ARMATURE_WORLD_Z_M,
        _sample_foot(index, 0), _sample_foot(index, RIGHT_LEAD_FRAMES),
    )
