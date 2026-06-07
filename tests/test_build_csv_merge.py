"""Tests for the deterministic merge/fix helpers in ``BuildCSV``.

``merge_waypoints_and_checkpoints`` (src/lib/build_csv.py:318) interleaves
wpt/cpt rows; ``fix_cpt_wpt_elevation_duplicates`` (src/lib/build_csv.py:336)
bumps a checkpoint elevation by +1 when it equals the following waypoint's.
Both are pandas-only and need no raster.
"""

import pandas as pd
import pytest

from src.lib.build_csv import BuildCSV


def _wpt(pid, elev, order):
    return {"point_id": pid, "type": "wpt", "geometry": None, "elev": elev, "order": order}


def _cpt(elev):
    return {"point_id": 0, "type": "cpt", "geometry": None, "elev": elev, "order": 0}


def test_merge_interleaves_wpt_cpt_ending_on_wpt():
    waypoints = pd.DataFrame([_wpt(1, 100, 1), _wpt(2, 110, 2), _wpt(3, 120, 3)])
    checkpoints = pd.DataFrame([_cpt(105), _cpt(115)])
    merged = BuildCSV("f", "d").merge_waypoints_and_checkpoints(waypoints, checkpoints)
    # 3 wpt + 2 cpt = 5 rows, pattern wpt,cpt,wpt,cpt,wpt
    assert list(merged["type"]) == ["wpt", "cpt", "wpt", "cpt", "wpt"]
    assert len(merged) == len(waypoints) + len(checkpoints)
    assert list(merged["point_id"]) == [1, 0, 2, 0, 3]


def test_fix_elevation_bumps_equal_cpt_before_wpt():
    df = pd.DataFrame(
        [
            _wpt(1, 100.0, 1),
            _cpt(110.0),  # equal to next wpt -> should become 111.0
            _wpt(2, 110.0, 2),
        ]
    )
    fixed = BuildCSV("f", "d").fix_cpt_wpt_elevation_duplicates(df)
    assert fixed.iloc[1]["elev"] == pytest.approx(111.0)
    # waypoint elevations untouched
    assert fixed.iloc[0]["elev"] == pytest.approx(100.0)
    assert fixed.iloc[2]["elev"] == pytest.approx(110.0)


def test_fix_elevation_leaves_distinct_values_alone():
    df = pd.DataFrame(
        [
            _wpt(1, 100.0, 1),
            _cpt(108.0),
            _wpt(2, 110.0, 2),
        ]
    )
    fixed = BuildCSV("f", "d").fix_cpt_wpt_elevation_duplicates(df)
    assert list(fixed["elev"]) == [100.0, 108.0, 110.0]
