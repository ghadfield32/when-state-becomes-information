from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class ReleaseEstimatorSettings:
    estimator_id: str
    window_seconds: float
    min_speed_m_s: float
    min_upward_velocity_m_s: float
    gravity_m_s2: float
    rim_height_m: float
    uncertainty_scope: str


@dataclass(frozen=True)
class BallisticFit3D:
    """Gravity-only local free-flight fit in a coordinate frame whose z axis is up."""

    reference_time_s: float
    position_m: np.ndarray       # position at reference_time_s
    velocity_m_s: np.ndarray     # velocity at reference_time_s
    rmse_m: float
    frame_indices: np.ndarray
    gravity_m_s2: float = 9.81

    def predict(self, time_s: np.ndarray | float) -> np.ndarray:
        t = np.asarray(time_s, dtype=np.float64) - self.reference_time_s
        t2 = np.atleast_1d(t)
        out = self.position_m[None, :] + t2[:, None] * self.velocity_m_s[None, :]
        out[:, 2] -= 0.5 * self.gravity_m_s2 * t2**2
        if np.ndim(time_s) == 0:
            return out[0]
        return out


def fit_gravity_ballistic_segment(
    time_s: np.ndarray,
    xyz_m: np.ndarray,
    *,
    frame_indices: np.ndarray | None = None,
    gravity_m_s2: float = 9.81,
) -> BallisticFit3D:
    """Fit p(t)=p0+v0*t+[0,0,-g]t^2/2 by least squares.

    This is deliberately a baseline. It does not model drag, Magnus force, wind,
    or contact. Its value is that deviations from it are interpretable.
    """
    time_s = np.asarray(time_s, dtype=np.float64)
    xyz_m = np.asarray(xyz_m, dtype=np.float64)
    if time_s.ndim != 1 or xyz_m.shape != (len(time_s), 3):
        raise ValueError("expected time_s [N] and xyz_m [N,3]")
    valid = np.isfinite(time_s) & np.isfinite(xyz_m).all(axis=1)
    if valid.sum() < 3:
        raise ValueError("need at least three valid 3D observations")

    t_abs = time_s[valid]
    p = xyz_m[valid]
    ref = float(t_abs[0])
    t = t_abs - ref
    corrected = p.copy()
    corrected[:, 2] += 0.5 * gravity_m_s2 * t**2
    design = np.column_stack([np.ones_like(t), t])
    beta, *_ = np.linalg.lstsq(design, corrected, rcond=None)
    p0 = beta[0]
    v0 = beta[1]

    pred = p0[None, :] + t[:, None] * v0[None, :]
    pred[:, 2] -= 0.5 * gravity_m_s2 * t**2
    rmse = float(np.sqrt(np.mean(np.sum((pred - p) ** 2, axis=1))))

    if frame_indices is None:
        frame_indices = np.arange(len(time_s), dtype=np.int64)
    frame_indices = np.asarray(frame_indices)[valid]

    return BallisticFit3D(
        reference_time_s=ref,
        position_m=p0,
        velocity_m_s=v0,
        rmse_m=rmse,
        frame_indices=frame_indices,
        gravity_m_s2=gravity_m_s2,
    )


def select_ballistic_window(
    time_s: np.ndarray,
    xyz_m: np.ndarray,
    *,
    frame_indices: np.ndarray | None = None,
    sampling_rate_hz: float,
    window_seconds: float = 0.12,
    min_speed_m_s: float = 2.0,
    min_upward_velocity_m_s: float = 0.25,
    gravity_m_s2: float = 9.81,
) -> BallisticFit3D:
    """Heuristic release/free-flight window selector.

    It scans contiguous valid windows and chooses the gravity-only fit with the
    smallest spatial residual among windows that look like a launched ball.
    This must be treated as an estimator with uncertainty, not ground truth.
    """
    time_s = np.asarray(time_s, dtype=np.float64)
    xyz_m = np.asarray(xyz_m, dtype=np.float64)
    if frame_indices is None:
        frame_indices = np.arange(len(time_s), dtype=np.int64)
    frame_indices = np.asarray(frame_indices)
    valid = np.isfinite(time_s) & np.isfinite(xyz_m).all(axis=1)

    n = max(4, int(round(window_seconds * sampling_rate_hz)))
    candidates: list[tuple[float, BallisticFit3D]] = []
    for start in range(0, len(time_s) - n + 1):
        sl = slice(start, start + n)
        if not valid[sl].all():
            continue
        if np.any(np.diff(frame_indices[sl]) != 1):
            continue
        fit = fit_gravity_ballistic_segment(
            time_s[sl], xyz_m[sl], frame_indices=frame_indices[sl], gravity_m_s2=gravity_m_s2
        )
        speed = float(np.linalg.norm(fit.velocity_m_s))
        if speed < min_speed_m_s or fit.velocity_m_s[2] < min_upward_velocity_m_s:
            continue
        # Slight preference for later equally-good windows because pre-release
        # human forcing can occasionally mimic a short parabola.
        score = fit.rmse_m - 1e-5 * float(frame_indices[start + n // 2])
        candidates.append((score, fit))

    if not candidates:
        raise ValueError("no plausible ballistic window found; inspect ball tracking/release manually")
    return min(candidates, key=lambda x: x[0])[1]


def crossing_at_height(
    fit: BallisticFit3D,
    height_m: float,
    *,
    descending: bool = True,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Return time, position and velocity when the fitted trajectory crosses z=height."""
    z0 = float(fit.position_m[2])
    vz0 = float(fit.velocity_m_s[2])
    g = float(fit.gravity_m_s2)
    # z0 + vz*t - .5*g*t^2 = height
    roots = np.roots([-0.5 * g, vz0, z0 - height_m])
    roots = [float(r.real) for r in roots if abs(r.imag) < 1e-9 and r.real >= 0]
    if not roots:
        raise ValueError("trajectory does not cross requested height in the future")

    eligible: list[float] = []
    for dt in roots:
        vz = vz0 - g * dt
        if (not descending) or vz < 0:
            eligible.append(dt)
    if not eligible:
        raise ValueError("no crossing matches requested descending/ascending direction")
    dt = max(eligible) if descending else min(eligible)
    t_abs = fit.reference_time_s + dt
    position = fit.predict(t_abs)
    velocity = fit.velocity_m_s.copy()
    velocity[2] -= g * dt
    return t_abs, position, velocity


def entry_angle_deg(velocity_m_s: np.ndarray) -> float:
    v = np.asarray(velocity_m_s, dtype=np.float64)
    horizontal = float(np.linalg.norm(v[:2]))
    return math.degrees(math.atan2(abs(float(v[2])), horizontal))
