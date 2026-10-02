"""Migrate the legacy release-angle table by CHECKING it against the closed form.

The user's legacy project carried a hardcoded 6x14 lookup of "optimal release angles".
Rather than transcribe those constants into a new module -- which would carry forward
numbers nobody can verify -- this script:

  1. recovers the legacy table from the quarantined source,
  2. asks which physical convention reproduces it,
  3. reports the residual against the derived minimum-speed solution, and
  4. states plainly whether the legacy numbers are reproduced, approximated, or not
     explained at all.

Step 2 matters because a mismatch is only meaningful once the convention is known. If
the legacy table assumed a different release-height baseline or a different target
height, comparing it against an assumed convention would produce a confident wrong
answer -- so several conventions are tested and reported, and the best is named.

Read-only with respect to the corpus and the quarantine: it reads the legacy file and
prints. It does not modify the legacy source.
"""
from __future__ import annotations

import ast
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wms.physics.release_angle import (  # noqa: E402
    REGULATION_RIM_HEIGHT_M,
    feet_to_metres,
    metres_to_feet,
    solve_minimum_speed_release,
)

LEGACY = (
    ROOT / "legacy" / "external" / "mlse_shot_feedback" / "489a6e1"
    / "src" / "freethrow_predictions" / "ml" / "feature_engineering"
    / "optimal_release_angle_metrics.py"
)

#: Orientation, read out of the legacy code rather than assumed -- and an earlier
#: version of THIS script got it backwards, which produced a confident "not explained"
#: verdict from a transposition error.
#:
#: The legacy call is `pd.DataFrame(data, index=heights)` where `heights` has 14 entries
#: (3.5 .. 10.0) and `data` has 6 keys. For a dict-of-lists pandas treats the KEYS as
#: COLUMNS and requires each list's length to equal the INDEX. So:
#:
#:     rows/index (14) = RELEASE HEIGHTS in feet, 3.5 .. 10.0
#:     columns    (6)  = DISTANCES to the basket in feet, 9 .. 24
#:     data[distance][height_index] = the angle
#:
#: The strongest confirmation is a hand-check: at a 10 ft release and 9 ft distance the
#: release is exactly at rim height, so the minimum-speed formula gives tan(theta) = 1,
#: i.e. 45.00 degrees -- which is the legacy value in that cell.
LEGACY_HEIGHTS_FT = (3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0)
LEGACY_DISTANCES_FT = (9, 11, 14, 17, 20, 24)


def _angle(table: dict[int, list[float]], height_ft: float, distance_ft: int) -> float:
    """One cell, with the orientation applied in exactly ONE place."""
    return table[distance_ft][LEGACY_HEIGHTS_FT.index(height_ft)]


def recover_legacy_table() -> dict[int, list[float]]:
    """Read the legacy table out of the quarantined source by PARSING it.

    Parsed rather than regex-scraped so a change in the legacy file's formatting cannot
    silently yield a different table. The literal is located by name, evaluated with
    `ast.literal_eval` (never `eval`), and its shape is asserted.
    """
    source = LEGACY.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "data" not in targets:
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        table = {}
        for key, value in zip(node.value.keys, node.value.values):
            k = ast.literal_eval(key)
            v = ast.literal_eval(value)
            if type(k) is not int:
                raise ValueError("distance coordinates must be integer feet")
            if k in table:
                raise ValueError(f"duplicate distance coordinate: {k}")
            table[k] = v
        validate_table(table)
        return table

    raise RuntimeError(
        f"could not recover a {len(LEGACY_DISTANCES_FT)}-column x {len(LEGACY_HEIGHTS_FT)}-row "
        f"table from {LEGACY}; the legacy source may have changed"
    )


def validate_table(table: dict[int, list[float]]) -> None:
    """Require the complete source grid; missing/invalid evidence cannot pass."""
    if not isinstance(table, dict) or set(table) != set(LEGACY_DISTANCES_FT):
        raise ValueError("expected exactly the six source distance coordinates")
    for distance, row in table.items():
        if type(distance) is not int:
            raise ValueError("distance coordinates must be integer feet")
        if not isinstance(row, list) or len(row) != len(LEGACY_HEIGHTS_FT):
            raise ValueError(f"distance {distance}: expected 14 release heights")
        for index, value in enumerate(row):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(
                    f"height {LEGACY_HEIGHTS_FT[index]} ft, distance {distance} ft: "
                    "expected a finite numeric angle"
                )


def main() -> int:
    try:
        table = recover_legacy_table()
        validate_table(table)
    except (ValueError, TypeError, OSError, SyntaxError, RuntimeError) as exc:
        print(f"VERDICT: INVALID -- {exc}")
        return 2
    print("=" * 76)
    print("LEGACY RELEASE-ANGLE TABLE: recovered and CHECKED against the closed form")
    print("=" * 76)
    print(f"source   : {LEGACY.relative_to(ROOT)}")
    print(f"shape    : {len(LEGACY_HEIGHTS_FT)} release heights x {len(table)} distances")
    print(f"heights  : {LEGACY_HEIGHTS_FT[0]}..{LEGACY_HEIGHTS_FT[-1]} ft")
    print(f"distances: {LEGACY_DISTANCES_FT[0]}..{LEGACY_DISTANCES_FT[-1]} ft")
    print()

    # --- which convention reproduces it? -------------------------------------
    #
    # The minimum-speed angle depends ONLY on release height, target height and
    # horizontal distance -- not on speed, mass or gravity. So if the legacy table is a
    # minimum-speed table, the only unknowns are which height baseline and which target
    # height were assumed. Both are tested rather than assumed.
    conventions: list[tuple[str, float, float]] = [
        ("target = 10 ft rim, heights as labelled", REGULATION_RIM_HEIGHT_M, 0.0),
        ("target = 10 ft rim, +1 ft above rim", REGULATION_RIM_HEIGHT_M + feet_to_metres(1), 0.0),
        ("target = 10 ft rim, -1 ft below rim", REGULATION_RIM_HEIGHT_M - feet_to_metres(1), 0.0),
        ("target = 14 ft (above the rim), heights as labelled",
         feet_to_metres(14), 0.0),
    ]

    sample = [(h, d) for h in (3.5, 7.0, 10.0) for d in (9, 17, 24)]
    best: tuple[str, float] | None = None
    print("Which convention reproduces the legacy numbers?")
    print(f"  {'convention':52} {'mean abs error (deg)':>21}")
    print("  " + "-" * 74)
    for label, target_m, _offset in conventions:
        errors = []
        for height_ft, distance_ft in sample:
            legacy = _angle(table, height_ft, distance_ft)
            solution = solve_minimum_speed_release(
                release_height_m=feet_to_metres(height_ft),
                target_height_m=target_m,
                horizontal_distance_m=feet_to_metres(distance_ft),
            )
            errors.append(abs(solution.angle_deg - legacy))
        if errors:
            mean = sum(errors) / len(errors)
            print(f"  {label:52} {mean:>21.3f}")
            if best is None or mean < best[1]:
                best = (label, mean)
    print()

    if best is None:
        print("VERDICT: INCONCLUSIVE -- no convention could be evaluated")
        return 2

    label, mean = best
    print(f"BEST: {label}  (mean abs error {mean:.3f} deg)")
    print()

    # --- the full residual for the best convention ---------------------------
    target_m = dict((c[0], c[1]) for c in conventions)[label]
    worst_error = 0.0
    worst_cell: tuple[float, int, float, float] | None = None
    total = 0.0
    count = 0
    violations = []
    for height_ft in LEGACY_HEIGHTS_FT:
        for distance_ft in LEGACY_DISTANCES_FT:
            legacy_value = _angle(table, height_ft, distance_ft)
            solution = solve_minimum_speed_release(
                release_height_m=feet_to_metres(height_ft),
                target_height_m=target_m,
                horizontal_distance_m=feet_to_metres(distance_ft),
            )
            residual = solution.angle_deg - legacy_value
            total += abs(residual)
            count += 1
            if worst_cell is None or abs(residual) > worst_error:
                worst_error = abs(residual)
                worst_cell = (height_ft, distance_ft, legacy_value, solution.angle_deg)
            # Nearest rounding to two decimals costs at most 0.005 degrees.
            # One ULP per operand covers their floating representation/arithmetic
            # at this scale, without granting an empirical extra tolerance.
            allowance = math.ulp(solution.angle_deg) + math.ulp(legacy_value)
            if abs(residual) > 0.005 + allowance:
                violations.append((height_ft, distance_ft, residual))
    assert worst_cell is not None
    print(f"full table    : {count} cells")
    print(f"mean abs error: {total / count:.4f} deg")
    print(f"worst cell    : height {worst_cell[0]} ft, distance {worst_cell[1]} ft -> "
          f"legacy {worst_cell[2]:.2f} deg vs derived {worst_cell[3]:.2f} deg ({worst_error:.3f} deg)")
    print(f"rounding gate : {count - len(violations)}/{count} cells within 0.005 deg + operand ULPs")
    for height_ft, distance_ft, residual in violations:
        print(f"OUTSIDE ROUNDING: height {height_ft} ft, distance {distance_ft} ft: {residual:+.9f} deg")
    print()

    # --- the asymptote, which is the checkable structural property ------------
    #
    # For fixed height difference, the closed form approaches 45 degrees as distance
    # grows. Equal release and target heights give 45 degrees at every distance.
    # This is a consistency check, not proof of how the original table was made.
    print("Structural check -- the near-distance behaviour:")
    print("  Equal release and target heights give tan(theta) = 1: 45.00 degrees.")
    print(f"  Below: 10 ft release against the selected {metres_to_feet(target_m):g} ft target.")
    for distance_ft in LEGACY_DISTANCES_FT:
        legacy_value = _angle(table, 10.0, distance_ft)
        derived = solve_minimum_speed_release(
            release_height_m=feet_to_metres(10.0),
            target_height_m=target_m,
            horizontal_distance_m=feet_to_metres(distance_ft),
        ).angle_deg
        print(f"    distance {distance_ft:>3} ft: legacy {legacy_value:>6.2f}  "
              f"derived {derived:>6.2f}  delta {legacy_value - derived:>+6.2f}")
    print("  A flat 45.00 row is consistent with equal-height minimum-speed mechanics;")
    print("  it does not establish the table's provenance or a player's best shooting form.")
    print()

    print("=" * 76)
    if not violations:
        print("VERDICT: REPRODUCED -- the legacy table is the minimum-speed solution")
        print("         under the best convention, within rounding of its 2 decimals.")
        print("         The migrated module computes it; the constants are not re-copied.")
        return 0
    print(f"VERDICT: NOT REPRODUCED -- {len(violations)} of {count} cells exceed source rounding")
    print(f"         full-table mean absolute error {total / count:.6f} deg; maximum {worst_error:.6f} deg.")
    print("         Choosing the best sampled convention does not validate the whole table.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
