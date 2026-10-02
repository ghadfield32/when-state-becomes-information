"""The migrated release-angle physics, and the check that it reproduces the legacy table.

Two things are being pinned here, and the second is the reason the migration exists:

1. The closed-form minimum-speed solution is correct and refuses bad input.
2. **It reproduces the user's legacy hardcoded table to 2-decimal rounding** — so the
   legacy constants are now a derived, checkable formula instead of magic numbers.

The second matters because the first attempt at this migration got the table's
ORIENTATION wrong (read the dict keys as heights when they are distances) and produced a
confident "NOT EXPLAINED, 9.5 deg error" verdict from a transposition. A transposition is
invisible from inside the code that contains it, so the reproduction is asserted here
rather than reported once in a console.
"""
from __future__ import annotations

import ast
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from wms.physics.release_angle import (  # noqa: E402
    REGULATION_RIM_HEIGHT_M,
    STANDARD_GRAVITY_M_S2,
    ReleaseAngleError,
    feet_to_metres,
    metres_to_feet,
    solve_minimum_speed_release,
)

ROWS_HEIGHTS_FT = (3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0)
COLS_DISTANCES_FT = (9, 11, 14, 17, 20, 24)

#: The legacy table, transcribed here so the test does not depend on the quarantine file.
#: `dict[distance][height_index]` -- verified against the source by
#: `test_the_transcribed_table_matches_the_legacy_source`.
LEGACY = {
    9: [62.92, 61.85, 60.71, 59.53, 58.28, 56.98, 55.63, 54.22, 52.76, 51.26, 49.73, 48.17, 46.59, 45.00],
    11: [60.29, 59.31, 58.28, 57.22, 56.12, 54.99, 53.83, 52.63, 51.40, 50.15, 48.88, 47.60, 46.30, 45.00],
    14: [57.45, 56.60, 55.72, 54.83, 53.91, 52.97, 52.02, 51.05, 50.06, 49.07, 48.06, 47.04, 46.02, 45.00],
    17: [55.46, 54.72, 53.96, 53.19, 52.41, 51.62, 50.82, 50.00, 49.18, 48.35, 47.52, 46.68, 45.84, 45.00],
    20: [54.00, 53.35, 52.69, 52.02, 51.34, 50.65, 49.96, 49.27, 48.56, 47.86, 47.14, 46.43, 45.72, 45.00],
    24: [52.58, 52.02, 51.45, 50.88, 50.31, 49.73, 49.15, 48.56, 47.97, 47.38, 46.79, 46.19, 45.60, 45.00],
}


def _derived(height_ft: float, distance_ft: int) -> float:
    return solve_minimum_speed_release(
        release_height_m=feet_to_metres(height_ft),
        target_height_m=REGULATION_RIM_HEIGHT_M,
        horizontal_distance_m=feet_to_metres(distance_ft),
    ).angle_deg


# --- the migration's whole point --------------------------------------------


def test_the_legacy_table_is_reproduced_to_its_stated_precision() -> None:
    """The migration claim, asserted rather than reported once.

    Every one of the 84 legacy cells must be reproduced within half of the table's last
    printed digit (0.005 deg), because 2-decimal rounding can cost at most that.
    """
    worst = 0.0
    for distance_ft, row in LEGACY.items():
        for height_ft, legacy_value in zip(ROWS_HEIGHTS_FT, row):
            worst = max(worst, abs(_derived(height_ft, distance_ft) - legacy_value))
    assert worst <= 0.005, (
        f"worst residual {worst:.4f} deg exceeds 2-decimal rounding; the legacy table is "
        "no longer reproduced and the migration must not claim that it is"
    )


def test_the_at_rim_height_row_is_exactly_45_degrees() -> None:
    """The hand-check that identifies the convention.

    At a 10 ft release the release point is exactly at rim height, so the closed form
    gives tan(theta) = 1 for EVERY distance -- a flat 45.00. That matches the legacy row
    exactly and is what distinguishes the correct orientation from the transpose.
    """
    for distance_ft in COLS_DISTANCES_FT:
        assert _derived(10.0, distance_ft) == pytest.approx(45.0, abs=1e-9)
        assert LEGACY[distance_ft][-1] == 45.00


def test_the_transposed_reading_does_NOT_reproduce_the_table() -> None:
    """A regression guard for the transposition that fooled the first attempt.

    Reading the six dict keys as release heights instead of distances moves the error
    from 0.002 deg to roughly 9 deg. Pinning that asymmetry means a future edit that
    transposes the table again fails here rather than producing a plausible report.
    """
    # `LEGACY[distance]` indexed by a HEIGHT is the transposed reading.
    transposed_errors = []
    for key in LEGACY:  # keys treated (wrongly) as heights
        for i, distance_ft in enumerate(COLS_DISTANCES_FT):  # positions treated as distances
            legacy_value = LEGACY[key][i]
            transposed_errors.append(
                abs(_derived(float(key), distance_ft) - legacy_value)
            )
    mean_transposed = sum(transposed_errors) / len(transposed_errors)
    assert mean_transposed > 5.0, (
        "the transposed reading should be badly wrong; if it now reproduces the table, "
        "the orientation constants are suspect"
    )


@pytest.mark.private_evidence
def test_the_transcribed_table_matches_the_legacy_source() -> None:
    """The local transcription must equal the quarantined original.

    Without this, the test above would happily pass against a table that no longer
    matches what the user's project actually contained.
    """
    legacy_path = (
        ROOT / "legacy" / "external" / "mlse_shot_feedback" / "489a6e1"
        / "src" / "freethrow_predictions" / "ml" / "feature_engineering"
        / "optimal_release_angle_metrics.py"
    )
    tree = ast.parse(legacy_path.read_text(encoding="utf-8"))
    recovered = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if "data" not in [t.id for t in node.targets if isinstance(t, ast.Name)]:
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        candidate = {}
        for key, value in zip(node.value.keys, node.value.values):
            if key is None:
                continue
            k = ast.literal_eval(key)
            v = ast.literal_eval(value)
            if isinstance(k, int) and isinstance(v, list) and len(v) == len(ROWS_HEIGHTS_FT):
                candidate[k] = [float(x) for x in v]
        if len(candidate) == len(COLS_DISTANCES_FT):
            recovered = candidate
            break

    assert recovered == LEGACY, "the transcribed table no longer matches the legacy source"


# --- the physics itself ------------------------------------------------------


def test_a_higher_release_needs_a_shallower_angle() -> None:
    """Monotonicity, which the legacy rows also show: later rows sit below earlier ones."""
    previous = None
    for height_ft in ROWS_HEIGHTS_FT:
        angle = _derived(height_ft, 15)
        if previous is not None:
            assert angle < previous
        previous = angle


def test_a_closer_shot_needs_a_steeper_angle() -> None:
    distances = (9, 11, 14, 17, 20, 24)
    angles = [_derived(7.0, d) for d in distances]
    assert angles == sorted(angles, reverse=True)


def test_the_speed_is_the_MINIMUM_and_is_achieved_by_that_angle() -> None:
    """The angle is only 'optimal' in the minimum-speed sense, so that must be true.

    Checked numerically: integrate the trajectory at the returned angle and speed and
    confirm it passes through the target, then confirm a slightly steeper or shallower
    launch at the same height cannot reach it more cheaply.
    """
    release_m, target_m, distance_m = feet_to_metres(7.0), REGULATION_RIM_HEIGHT_M, feet_to_metres(15.0)
    solution = solve_minimum_speed_release(release_m, target_m, distance_m)

    # 1. The trajectory passes through the target point.
    vx = solution.speed_m_s * math.cos(solution.angle_rad)
    vy = solution.speed_m_s * math.sin(solution.angle_rad)
    t = distance_m / vx
    y_at_target = release_m + vy * t - 0.5 * STANDARD_GRAVITY_M_S2 * t * t
    assert y_at_target == pytest.approx(target_m, abs=1e-9)

    # 2. No smaller speed reaches it at this height.
    for delta_deg in (-2.0, -1.0, 1.0, 2.0):
        angle = solution.angle_rad + math.radians(delta_deg)
        # Minimum speed at a FIXED angle that just reaches the target.
        denom = 2.0 * math.cos(angle) ** 2 * (distance_m * math.tan(angle) - (target_m - release_m))
        if denom <= 0:
            continue
        fixed_angle_speed = math.sqrt(STANDARD_GRAVITY_M_S2 * distance_m * distance_m / denom)
        assert fixed_angle_speed > solution.speed_m_s


# --- refusals, typed rather than defaulted -----------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"release_height_m": 0.0, "target_height_m": 3.048, "horizontal_distance_m": 0.0},
        {"release_height_m": 0.0, "target_height_m": 3.048, "horizontal_distance_m": -1.0},
        {"release_height_m": float("nan"), "target_height_m": 3.048, "horizontal_distance_m": 1.0},
        {"release_height_m": 0.0, "target_height_m": float("inf"), "horizontal_distance_m": 1.0},
        {"release_height_m": 0.0, "target_height_m": 3.048, "horizontal_distance_m": 1.0,
         "gravity_m_s2": 0.0},
    ],
)
def test_bad_input_is_refused_not_defaulted(kwargs) -> None:
    """The legacy example returned `None` on error, which is indistinguishable from a
    computed value at the call site -- the failure-masking pattern this repo forbids."""
    with pytest.raises(ReleaseAngleError):
        solve_minimum_speed_release(**kwargs)


def test_unit_conversion_is_exact_by_definition() -> None:
    assert feet_to_metres(1.0) == pytest.approx(0.3048, abs=1e-12)
    assert metres_to_feet(0.3048) == pytest.approx(1.0, abs=1e-12)
    assert metres_to_feet(feet_to_metres(7.0)) == pytest.approx(7.0, abs=1e-12)


@pytest.mark.parametrize("distance", COLS_DISTANCES_FT)
@pytest.mark.parametrize("index", range(14))
@pytest.mark.parametrize("delta", [0.1, 10.0])
def test_report_rejects_and_locates_each_corrupted_cell(monkeypatch, capsys, distance, index, delta):
    import migrate_legacy_release_angle as report
    table = {d: list(row) for d, row in LEGACY.items()}
    table[distance][index] += delta
    monkeypatch.setattr(report, "recover_legacy_table", lambda: table)
    assert report.main() == 1
    output = capsys.readouterr().out
    assert "VERDICT: REPRODUCED" not in output
    assert f"height {ROWS_HEIGHTS_FT[index]} ft, distance {distance} ft" in output


def test_report_reference_shape_and_success(monkeypatch, capsys):
    import migrate_legacy_release_angle as report
    monkeypatch.setattr(report, "recover_legacy_table", lambda: LEGACY)
    assert report.main() == 0
    output = capsys.readouterr().out
    assert "14 release heights x 6 distances" in output
    assert "84 cells" in output
    assert "VERDICT: REPRODUCED" in output


@pytest.mark.parametrize("defect", ["missing", "extra", "short", "long", "nan", "inf", "text", "bool"])
def test_report_invalid_table_refuses(monkeypatch, capsys, defect):
    import migrate_legacy_release_angle as report
    table = {d: list(row) for d, row in LEGACY.items()}
    if defect == "missing":
        del table[11]
    elif defect == "extra":
        table[12] = list(table[11])
    elif defect == "short":
        table[11].pop()
    elif defect == "long":
        table[11].append(45.0)
    else:
        table[11][1] = {"nan": float("nan"), "inf": float("inf"), "text": "unknown", "bool": True}[defect]
    monkeypatch.setattr(report, "recover_legacy_table", lambda: table)
    assert report.main() == 2
    assert "VERDICT: INVALID" in capsys.readouterr().out


@pytest.mark.parametrize("excess,expected", [(0.0, 0), (1e-10, 1)])
def test_report_rounding_boundary(monkeypatch, capsys, excess, expected):
    import migrate_legacy_release_angle as report
    table = {d: [_derived(h, d) for h in ROWS_HEIGHTS_FT] for d in COLS_DISTANCES_FT}
    table[11][1] += 0.005 + excess
    monkeypatch.setattr(report, "recover_legacy_table", lambda: table)
    assert report.main() == expected
    assert ("VERDICT: REPRODUCED" in capsys.readouterr().out) == (expected == 0)


def test_report_exact_formula_table(monkeypatch, capsys):
    import migrate_legacy_release_angle as report
    table = {d: [_derived(h, d) for h in ROWS_HEIGHTS_FT] for d in COLS_DISTANCES_FT}
    monkeypatch.setattr(report, "recover_legacy_table", lambda: table)
    assert report.main() == 0
    assert "VERDICT: REPRODUCED" in capsys.readouterr().out


def test_legacy_reader_rejects_duplicate_distance(tmp_path, monkeypatch):
    import migrate_legacy_release_angle as report
    source = tmp_path / "legacy.py"
    entries = [f"{d}: {row!r}" for d, row in LEGACY.items()]
    entries.append(f"11: {LEGACY[11]!r}")
    source.write_text("data = {" + ",".join(entries) + "}", encoding="utf-8")
    monkeypatch.setattr(report, "LEGACY", source)
    with pytest.raises(ValueError, match="duplicate"):
        report.recover_legacy_table()


@pytest.mark.parametrize("delta,expected", [(0.0, 0), (0.1, 1), (10.0, 1)])
def test_report_process_verdict_matches_exit_code(delta, expected):
    import subprocess
    code = (
        "import sys; sys.path.insert(0, 'scripts'); "
        "import migrate_legacy_release_angle as r; "
        f"table={LEGACY!r}; "
        f"table[11][1]+={delta!r}; "
        "r.recover_legacy_table=lambda:table; raise SystemExit(r.main())"
    )
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == expected, result.stderr
    assert ("VERDICT: REPRODUCED" in result.stdout) == (expected == 0)
    verdict = "REPRODUCED" if expected == 0 else "NOT REPRODUCED"
    assert f"VERDICT: {verdict} --" in result.stdout, result.stderr
    assert not result.stderr
    if expected != 0:
        assert "OUTSIDE ROUNDING: height 4.0 ft, distance 11 ft:" in result.stdout


@pytest.mark.parametrize("distance", [11.0, "11"])
def test_reader_rejects_invalid_distance_coordinates(tmp_path, monkeypatch, distance):
    import migrate_legacy_release_angle as report
    table = {d: list(row) for d, row in LEGACY.items() if d != 11}
    table[distance] = list(LEGACY[11])
    source = tmp_path / "legacy.py"
    source.write_text("data = " + repr(table), encoding="utf-8")
    monkeypatch.setattr(report, "LEGACY", source)
    with pytest.raises(ValueError):
        report.recover_legacy_table()


@pytest.mark.parametrize("index", range(14))
@pytest.mark.parametrize("distance", COLS_DISTANCES_FT)
@pytest.mark.parametrize("excess,expected", [(-1e-10, 0), (0.0, 0), (1e-10, 1)])
def test_report_boundary_at_every_coordinate(monkeypatch, capsys, index, distance, excess, expected):
    import migrate_legacy_release_angle as report
    table = {d: [_derived(h, d) for h in ROWS_HEIGHTS_FT] for d in COLS_DISTANCES_FT}
    table[distance][index] += 0.005 + excess
    # At these angles the allowance is many orders smaller than 1e-10.
    allowance = math.ulp(_derived(ROWS_HEIGHTS_FT[index], distance)) + math.ulp(table[distance][index])
    assert allowance < 1e-12
    monkeypatch.setattr(report, "recover_legacy_table", lambda: table)
    assert report.main() == expected
    assert ("VERDICT: REPRODUCED" in capsys.readouterr().out) == (expected == 0)


@pytest.mark.parametrize("target_ft", [9.0, 10.0, 11.0, 14.0])
def test_report_accepts_each_supported_convention(monkeypatch, capsys, target_ft):
    import migrate_legacy_release_angle as report
    table = {d: [round(solve_minimum_speed_release(feet_to_metres(h), feet_to_metres(target_ft), feet_to_metres(d)).angle_deg, 2)
                 for h in ROWS_HEIGHTS_FT] for d in COLS_DISTANCES_FT}
    monkeypatch.setattr(report, "recover_legacy_table", lambda: table)
    assert report.main() == 0
    assert "VERDICT: REPRODUCED" in capsys.readouterr().out
