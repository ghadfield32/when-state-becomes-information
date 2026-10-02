from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np

FEET_TO_METERS = 0.3048
INCHES_TO_METERS = 0.0254


def _xyz_or_nan(value: Any) -> np.ndarray:
    if value is None or not isinstance(value, (list, tuple)) or len(value) != 3:
        return np.full(3, np.nan, dtype=np.float64)
    out = np.asarray(value, dtype=np.float64)
    if out.shape != (3,):
        return np.full(3, np.nan, dtype=np.float64)
    return out


@dataclass(frozen=True)
class SPLFreeThrowTrial:
    """Canonical in-memory representation of one MLSE SPL free-throw JSON trial.

    Geometry is converted to SI units at ingestion while the original hoop-plane
    labels are preserved in their documented units as well. Missing measurements
    remain NaN; ingestion never silently interpolates them.
    """

    sampling_rate_hz: float
    trial_date: str
    participant_id: str
    trial_id: str
    result: str
    landing_x_in: float
    landing_y_in: float
    entry_angle_deg: float
    frame_index: np.ndarray          # [T]
    time_s: np.ndarray               # [T]
    ball_xyz_m: np.ndarray           # [T, 3]
    player_xyz_m: np.ndarray         # [T, J, 3]
    keypoint_names: tuple[str, ...]

    def __post_init__(self) -> None:
        t = len(self.time_s)
        if self.frame_index.shape != (t,):
            raise ValueError("frame_index must have shape [T]")
        if self.ball_xyz_m.shape != (t, 3):
            raise ValueError("ball_xyz_m must have shape [T, 3]")
        if self.player_xyz_m.shape != (t, len(self.keypoint_names), 3):
            raise ValueError("player_xyz_m must have shape [T, J, 3]")
        if t and np.any(np.diff(self.time_s) < 0):
            raise ValueError("time_s must be monotonic nondecreasing")

    @property
    def made(self) -> bool:
        return self.result.lower() == "made"

    @property
    def ball_valid_mask(self) -> np.ndarray:
        return np.isfinite(self.ball_xyz_m).all(axis=1)

    @property
    def left_right_in(self) -> float:
        """Alias used by the 2026 SPLxUTSPAN documentation: x is left/right."""
        return self.landing_x_in

    @property
    def depth_in(self) -> float:
        """Alias used by the 2026 SPLxUTSPAN documentation: y is hoop depth."""
        return self.landing_y_in

    def keypoint(self, name: str) -> np.ndarray:
        try:
            idx = self.keypoint_names.index(name)
        except ValueError as exc:
            raise KeyError(name) from exc
        return self.player_xyz_m[:, idx, :]

    def metric_outcome(self) -> dict[str, float]:
        return {
            "left_right_m": self.left_right_in * INCHES_TO_METERS,
            "depth_m": self.depth_in * INCHES_TO_METERS,
            "entry_angle_deg": self.entry_angle_deg,
        }


def load_spl_free_throw(path: str | Path) -> SPLFreeThrowTrial:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    tracking = payload.get("tracking")
    if not isinstance(tracking, list) or not tracking:
        raise ValueError("SPL trial must contain a non-empty tracking list")

    # Keep first-seen order so tensors stay deterministic even when a later frame
    # contains a keypoint that was absent from frame 0.
    names: list[str] = []
    seen: set[str] = set()
    for row in tracking:
        player = ((row or {}).get("data") or {}).get("player") or {}
        for name in player:
            if name not in seen:
                names.append(name)
                seen.add(name)

    t = len(tracking)
    frame_index = np.empty(t, dtype=np.int64)
    time_s = np.empty(t, dtype=np.float64)
    ball = np.full((t, 3), np.nan, dtype=np.float64)
    player = np.full((t, len(names), 3), np.nan, dtype=np.float64)
    name_to_idx = {name: i for i, name in enumerate(names)}

    for i, row in enumerate(tracking):
        frame_index[i] = int(row.get("frame", i))
        # SPL JSON stores this field in milliseconds.
        time_s[i] = float(row.get("time", 1000.0 * i / float(payload["sampling_rate"]))) / 1000.0
        data = row.get("data") or {}
        ball[i] = _xyz_or_nan(data.get("ball")) * FEET_TO_METERS
        for name, value in (data.get("player") or {}).items():
            player[i, name_to_idx[name]] = _xyz_or_nan(value) * FEET_TO_METERS

    return SPLFreeThrowTrial(
        sampling_rate_hz=float(payload["sampling_rate"]),
        trial_date=str(payload.get("trial_date", "")),
        participant_id=str(payload["participant_id"]),
        trial_id=str(payload["trial_id"]),
        result=str(payload.get("result", "unknown")),
        landing_x_in=float(payload.get("landing_x", np.nan)),
        landing_y_in=float(payload.get("landing_y", np.nan)),
        entry_angle_deg=float(payload.get("entry_angle", np.nan)),
        frame_index=frame_index,
        time_s=time_s,
        ball_xyz_m=ball,
        player_xyz_m=player,
        keypoint_names=tuple(names),
    )
