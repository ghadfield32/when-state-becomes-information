"""Minimum-speed release angle for a ballistic free throw (migrated from the legacy example).

**Why this is derived rather than transcribed.** The user's legacy project
(`spl_freethrow_biomechanics_analysis_ml_prediction`) carried a *hardcoded* 6x14 lookup
table of "optimal release angles" keyed by release height and distance. A table of
constants cannot be checked, cannot be unit-converted, and silently clamps outside its
range. The quantity it approximates has a **closed form**, so this module computes it
and the migration script verifies the legacy numbers against it -- rather than copying
magic values into a new file and calling that a migration.

**The physics.** For a projectile launched from height ``h`` that must pass through a
point at height ``H`` a horizontal distance ``d`` away, the *minimum* launch speed and
the angle that achieves it are

    tan(theta) = (dz + sqrt(dz^2 + d^2)) / d
    v_min^2    = g * (dz + sqrt(dz^2 + d^2))

where ``dz = H - h`` (negative when the target is below the release point, which is the
normal case for a shot released above the rim). ``theta`` is measured from the
horizontal, above it.

**This is a kinematics result, not a model of a basketball shot.** It ignores drag,
spin, the backboard, the ball's radius, and any release-to-rim horizontal offset. It
describes the *minimum-speed* solution for a point projectile, which is a useful
reference and a checkable baseline -- **not** a description of what any athlete did or
should do. ``optimal`` in the legacy naming means "minimum speed", and that is the
sense preserved here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

#: Standard gravity, m/s^2. A declared constant rather than a literal at the call site,
#: so a reader can see which value was used.
STANDARD_GRAVITY_M_S2 = 9.80665

#: A regulation basketball hoop is 10 ft (3.048 m) above the floor.
REGULATION_RIM_HEIGHT_M = 3.048


@dataclass(frozen=True)
class ReleaseSolution:
    """The minimum-speed launch that passes through the target point."""

    release_height_m: float
    target_height_m: float
    horizontal_distance_m: float
    angle_rad: float
    angle_deg: float
    speed_m_s: float

    @property
    def rise_m(self) -> float:
        """Vertical gain from release to target. Negative means the target is below."""
        return self.target_height_m - self.release_height_m

    def as_dict(self) -> dict[str, float]:
        return {
            "release_height_m": self.release_height_m,
            "target_height_m": self.target_height_m,
            "horizontal_distance_m": self.horizontal_distance_m,
            "rise_m": self.rise_m,
            "angle_rad": self.angle_rad,
            "angle_deg": self.angle_deg,
            "speed_m_s": self.speed_m_s,
        }


class ReleaseAngleError(ValueError):
    """A refused input. Typed, so a caller cannot mistake it for a computed value."""


def solve_minimum_speed_release(
    release_height_m: float,
    target_height_m: float,
    horizontal_distance_m: float,
    *,
    gravity_m_s2: float = STANDARD_GRAVITY_M_S2,
) -> ReleaseSolution:
    """Minimum-speed launch angle and speed to pass through the target point.

    All inputs are SI metres. Raises ``ReleaseAngleError`` rather than returning a
    default, because the legacy example returned ``None`` on error -- which is
    indistinguishable from a computed value at the call site, and is the failure-masking
    pattern this repository forbids.
    """
    if not math.isfinite(release_height_m) or not math.isfinite(target_height_m):
        raise ReleaseAngleError("heights must be finite")
    if not math.isfinite(horizontal_distance_m):
        raise ReleaseAngleError("horizontal distance must be finite")
    if horizontal_distance_m == 0:
        # Straight up or straight down. The minimum-speed formula divides by d, and the
        # degenerate case has no unique angle, so it is refused rather than approximated.
        raise ReleaseAngleError(
            "horizontal_distance_m is 0: the minimum-speed angle is undefined for a "
            "vertical shot; the formula divides by the horizontal distance"
        )
    if horizontal_distance_m < 0:
        raise ReleaseAngleError(
            "horizontal_distance_m is negative: the target must be in front of the "
            "release point (pass a positive distance with the correct sign convention)"
        )
    if not math.isfinite(gravity_m_s2) or gravity_m_s2 <= 0:
        raise ReleaseAngleError("gravity must be finite and positive")

    rise = target_height_m - release_height_m
    root = math.hypot(rise, horizontal_distance_m)  # sqrt(dz^2 + d^2), overflow-safe
    tan_theta = (rise + root) / horizontal_distance_m

    # `root > |rise|` strictly whenever d > 0, so `rise + root > 0` and the angle is
    # always in (0, pi/2). No quadrant handling is needed, and asserting that here
    # documents why.
    if tan_theta <= 0:  # pragma: no cover - unreachable given the checks above
        raise ReleaseAngleError("non-positive tang; this indicates a bad input")

    angle_rad = math.atan(tan_theta)
    # v^2 = g * (dz + sqrt(dz^2 + d^2)) is >= 0 because the bracket equals tan_theta * d
    # and both are positive, so this sqrt cannot fail.
    speed = math.sqrt(gravity_m_s2 * (rise + root))

    return ReleaseSolution(
        release_height_m=release_height_m,
        target_height_m=target_height_m,
        horizontal_distance_m=horizontal_distance_m,
        angle_rad=angle_rad,
        angle_deg=math.degrees(angle_rad),
        speed_m_s=speed,
    )


def feet_to_metres(feet: float) -> float:
    """Exact by definition: 1 ft = 0.3048 m (the international foot)."""
    return feet * 0.3048


def metres_to_feet(metres: float) -> float:
    return metres / 0.3048


def release_height_for_rise(hoop_height_m: float, rise_m: float) -> float:
    """Release height implied by a rise, for testing a hypothesis about legacy data."""
    return hoop_height_m - rise_m
