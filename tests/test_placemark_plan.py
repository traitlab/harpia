"""Tests for the placemark sequence shared by template.kml and waylines.wpml."""

from src.lib.placemark_plan import (
    APPROACH,
    FIRST,
    LAST,
    PHOTO,
    TOUCH_SKY,
    placemark_plan,
    step_height,
)

# (lat_y, lon_x, elevation_from_dsm, point_id), as the builders read the CSV.
WPTS = [
    ("46.0", "-74.0", "100", "1"),
    ("46.1", "-74.1", "110", "2"),
    ("46.2", "-74.2", "112", "3"),
]
# One checkpoint per leg, plus a copy at each end, as setup() lays them out.
CPTS = [
    ("46.0", "-74.0", "105", "0"),
    ("46.0", "-74.0", "105", "0"),
    ("46.1", "-74.1", "108", "0"),
    ("46.1", "-74.1", "108", "0"),
]


def test_four_placemarks_per_waypoint():
    steps = placemark_plan(WPTS, CPTS, 6, 10)
    assert [s.kind for s in steps] == [FIRST, APPROACH, PHOTO, LAST] * len(WPTS)
    assert [s.wpt for s in steps] == [0] * 4 + [1] * 4 + [2] * 4


def test_heights_follow_checkpoints_and_waypoints():
    steps = placemark_plan(WPTS, CPTS, 6, 10)
    heights = [step_height(s.elevation, s.offsets) for s in steps[4:8]]
    # Waypoint 2: entered through checkpoint 1, left through checkpoint 2.
    assert heights == ["121.0", "126.0", "116.0", "124.0"]


def test_gimbal_down_on_arrival_ahead_on_departure():
    steps = placemark_plan(WPTS, CPTS, 6, 10)
    assert steps[0].gimbal == "-90"
    assert steps[3].gimbal == "-15"


def test_touch_sky_after_interval():
    steps = placemark_plan(WPTS, CPTS, 6, 10, touch_sky=True, touch_sky_interval=2)
    kinds = [s.kind for s in steps]
    tree = [FIRST, APPROACH, PHOTO, LAST]
    assert kinds == tree + tree + [TOUCH_SKY, LAST] + tree
    touch = steps[8]
    assert touch.wpt == 1
    assert step_height(touch.elevation, touch.offsets) == "208.0"
