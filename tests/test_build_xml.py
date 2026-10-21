"""Tests for the DJI KML/WPML XML generation.

``BuildTemplateKML`` (src/lib/build_template_kml.py:14) and
``BuildWaylinesWPML`` (src/lib/build_waylines_wpml.py:11) read the waypoints CSV,
clone the bundled template, and emit one Placemark block per (wpt, cpt) sequence.
Both write into ``{output_folder}/{output_filename}/wpmz/``.

Each waypoint expands to 4 placemarks when touch-sky is off:
firstLast (approach-from), approach, photos, firstLast (depart-to).
"""

import xml.etree.ElementTree as ET

import pytest
from conftest import write_waypoint_csv
from pydantic import ValidationError

from src.lib.build_template_kml import BuildTemplateKML
from src.lib.build_waylines_wpml import BuildWaylinesWPML
from src.lib.photo_heading import photo_headings
from src.model.config import Config

NS = {
    "kml": "http://www.opengis.net/kml/2.2",
    "wpml": "http://www.dji.com/wpmz/1.0.6",
}

# 3 waypoints, 2 checkpoints (the wpt = cpt + 1 invariant the builders require).
WPT_ROWS = [
    (1, -74.000, 46.0000, 100, 1),
    (2, -74.002, 46.0010, 110, 2),
    (3, -74.004, 46.0020, 112, 3),
]
CPT_ROWS = [
    (0, -74.001, 46.0005, 105, 0),
    (0, -74.003, 46.0015, 108, 0),
]


@pytest.fixture
def csv_path(tmp_path):
    return write_waypoint_csv(tmp_path / "site_points.csv", WPT_ROWS, CPT_ROWS)


def _placemarks(folder):
    return folder.findall("kml:Placemark", NS)


def test_wpml_placemark_count_is_four_per_waypoint(configured, csv_path):
    configured.csv_path = csv_path
    b = BuildWaylinesWPML()
    b.setup()
    b.generate()
    assert len(b.wpt_csv_properties) == len(WPT_ROWS)
    assert len(_placemarks(b.folder)) == 4 * len(WPT_ROWS)


def test_wpml_required_dji_elements_present(configured, csv_path):
    configured.csv_path = csv_path
    b = BuildWaylinesWPML()
    b.setup()
    b.generate()
    placemarks = _placemarks(b.folder)
    first = placemarks[0]
    # Required WPML waypoint elements.
    assert first.find("wpml:index", NS) is not None
    assert first.find("wpml:executeHeight", NS) is not None
    assert first.find("wpml:waypointSpeed", NS) is not None
    assert first.find("wpml:actionGroup", NS) is not None
    # waypointSpeed reflects the wayline's autoFlightSpeed for fly-through pts.
    assert first.find("wpml:waypointSpeed", NS).text == b.waypointSpeed
    # indices run 0..N-1 contiguously across all placemarks.
    indices = [int(p.find("wpml:index", NS).text) for p in placemarks]
    assert indices == list(range(len(placemarks)))


@pytest.mark.parametrize(("model", "speed"), [("m3e", "15"), ("m4e", "21"), ("m4d", "21")])
def test_wpml_transit_speed_matches_wayline_speed(configured, csv_path, model, speed):
    configured.csv_path = csv_path
    configured.drone_model = model
    b = BuildWaylinesWPML()
    b.setup()
    b.generate()
    # Transit waypoints fly at the wayline speed, which differs by model.
    assert b.folder.find("wpml:autoFlightSpeed", NS).text == speed
    speeds = [p.find("wpml:waypointSpeed", NS).text for p in _placemarks(b.folder)]
    assert set(speeds) == {speed, b.waypointSpeed_approach}
    # Only the approach waypoint, index 1 of each group of 4, slows down.
    assert speeds[1::4] == [b.waypointSpeed_approach] * len(WPT_ROWS)


def test_wpml_coordinates_passthrough(configured, csv_path):
    configured.csv_path = csv_path
    b = BuildWaylinesWPML()
    b.setup()
    b.generate()
    coord = _placemarks(b.folder)[0].find("kml:Point/kml:coordinates", NS).text
    lon, lat = coord.split(",")
    # First waypoint coordinates carried through as "lon,lat".
    assert float(lon) == pytest.approx(WPT_ROWS[0][1])
    assert float(lat) == pytest.approx(WPT_ROWS[0][2])


def test_kml_placemark_count_and_photo_actions(configured, csv_path):
    configured.csv_path = csv_path
    configured.drone_model = "m3e"
    b = BuildTemplateKML()
    b.setup()
    b.generate()
    placemarks = _placemarks(b.folder)
    assert len(placemarks) == 4 * len(WPT_ROWS)
    # The photos placemark (index 2 of each group of 4) carries orientedShoot
    # actions: m3e has 2 photo actions (tele + wide).
    photos_pm = placemarks[2]
    shoots = photos_pm.findall(
        "wpml:actionGroup/wpml:action[wpml:actionActuatorFunc='orientedShoot']", NS
    )
    assert len(shoots) == 2


def _local_tags(param):
    return [child.tag.split("}")[-1] for child in param]


def test_kml_m4e_has_three_photo_actions(configured, csv_path):
    configured.csv_path = csv_path
    configured.drone_model = "m4e"
    b = BuildTemplateKML()
    b.setup()
    b.generate()
    photos_pm = _placemarks(b.folder)[2]
    group = photos_pm.find("wpml:actionGroup", NS)
    # m4e: tele + med via orientedShoot, wide via takePhoto (needed for RTK).
    shoots = group.findall("wpml:action[wpml:actionActuatorFunc='orientedShoot']", NS)
    assert len(shoots) == 2
    photos = group.findall("wpml:action[wpml:actionActuatorFunc='takePhoto']", NS)
    assert len(photos) == 1
    param = photos[0].find("wpml:actionActuatorFuncParam", NS)
    # Element set and order as emitted by the RC: template.kml carries no lens index.
    assert _local_tags(param) == [
        "fileSuffix",
        "payloadPositionIndex",
        "useGlobalPayloadLensIndex",
    ]
    assert param.find("wpml:fileSuffix", NS).text.endswith("wide")
    # The M4E RC leaves the lens index out of template.kml entirely.
    shoot = shoots[0].find("wpml:actionActuatorFuncParam", NS)
    assert shoot.find("wpml:payloadLensIndex", NS) is None
    # template.kml has no focus action; that one is waylines-only.
    assert group.findall("wpml:action[wpml:actionActuatorFunc='focus']", NS) == []


def test_wpml_m4e_takephoto_matches_rc_export(configured, csv_path):
    configured.csv_path = csv_path
    configured.drone_model = "m4e"
    b = BuildWaylinesWPML()
    b.setup()
    b.generate()
    group = _placemarks(b.folder)[2].find("wpml:actionGroup", NS)
    actions = group.findall("wpml:action", NS)
    funcs = [a.find("wpml:actionActuatorFunc", NS).text for a in actions]
    # The RC precedes takePhoto with a centred focus action.
    assert funcs == ["orientedShoot", "orientedShoot", "focus", "takePhoto"]
    # actionIds run 0..N-1 contiguously, focus included.
    assert [a.find("wpml:actionId", NS).text for a in actions] == ["0", "1", "2", "3"]

    param = actions[3].find("wpml:actionActuatorFuncParam", NS)
    assert _local_tags(param) == [
        "fileSuffix",
        "payloadPositionIndex",
        "useGlobalPayloadLensIndex",
        "payloadLensIndex",
    ]
    assert param.find("wpml:fileSuffix", NS).text.endswith("wide")
    # "visable" is DJI's own spelling, as emitted by the RC.
    assert param.find("wpml:payloadLensIndex", NS).text == "visable"

    # The M4E RC does write the lens index on orientedShoot in waylines.wpml.
    shoot = actions[0].find("wpml:actionActuatorFuncParam", NS)
    assert shoot.find("wpml:payloadLensIndex", NS).text == "visable"

    focus = actions[2].find("wpml:actionActuatorFuncParam", NS)
    assert focus.find("wpml:focusX", NS).text == "0.25"
    assert focus.find("wpml:focusRegionWidth", NS).text == "0.5"


def test_kml_m4d_matches_rc_export(configured, csv_path):
    configured.csv_path = csv_path
    configured.drone_model = "m4d"
    b = BuildTemplateKML()
    b.setup()
    b.generate()
    # Mission header comes straight from templates/m4d-onewpt-wpmz/template.kml.
    assert b.root.find(".//wpml:droneEnumValue", NS).text == "100"
    assert b.root.find(".//wpml:payloadEnumValue", NS).text == "98"

    group = _placemarks(b.folder)[2].find("wpml:actionGroup", NS)
    actions = group.findall("wpml:action", NS)
    funcs = [a.find("wpml:actionActuatorFunc", NS).text for a in actions]
    # Same three-shot sequence as the M4E; no focus action in template.kml.
    assert funcs == ["orientedShoot", "orientedShoot", "takePhoto"]

    shoot = actions[0].find("wpml:actionActuatorFuncParam", NS)
    assert shoot.find("wpml:orientedCameraType", NS).text == "98"
    # Unlike the M4E, the M4D RC writes the lens index into template.kml too.
    assert shoot.find("wpml:payloadLensIndex", NS).text == "visable"
    photo = actions[2].find("wpml:actionActuatorFuncParam", NS)
    assert _local_tags(photo) == [
        "fileSuffix",
        "payloadPositionIndex",
        "useGlobalPayloadLensIndex",
        "payloadLensIndex",
    ]


def test_wpml_m4d_matches_rc_export(configured, csv_path):
    configured.csv_path = csv_path
    configured.drone_model = "m4d"
    b = BuildWaylinesWPML()
    b.setup()
    b.generate()
    assert b.root.find(".//wpml:droneEnumValue", NS).text == "100"
    assert b.root.find(".//wpml:payloadEnumValue", NS).text == "98"

    actions = _placemarks(b.folder)[2].find("wpml:actionGroup", NS).findall("wpml:action", NS)
    funcs = [a.find("wpml:actionActuatorFunc", NS).text for a in actions]
    assert funcs == ["orientedShoot", "orientedShoot", "focus", "takePhoto"]

    shoot = actions[0].find("wpml:actionActuatorFuncParam", NS)
    assert shoot.find("wpml:orientedCameraType", NS).text == "98"
    assert shoot.find("wpml:payloadLensIndex", NS).text == "visable"
    photo = actions[3].find("wpml:actionActuatorFuncParam", NS)
    assert photo.find("wpml:payloadLensIndex", NS).text == "visable"


STOP_TURN = "toPointAndStopWithDiscontinuityCurvature"


def test_kml_turn_mode_matches_rc_export(configured, csv_path):
    configured.csv_path = csv_path
    b = BuildTemplateKML()
    b.setup()
    b.generate()
    # The Folder-level turn mode is carried over from template.kml unchanged.
    assert b.root.find(".//wpml:globalWaypointTurnMode", NS).text == "coordinateTurn"

    placemarks = _placemarks(b.folder)
    for i, pm in enumerate(placemarks):
        turn_param = pm.find("wpml:waypointTurnParam", NS)
        use_global = pm.find("wpml:useGlobalTurnParam", NS)
        if i % 4 == 2:
            # Photo waypoint: overrides the global coordinateTurn so the
            # aircraft holds still for the whole burst.
            assert use_global is None
            assert turn_param.find("wpml:waypointTurnMode", NS).text == STOP_TURN
            assert turn_param.find("wpml:waypointTurnDampingDist", NS).text == "0"
        else:
            # Every other waypoint defers to the global coordinateTurn.
            assert turn_param is None
            assert use_global.text == "1"


def test_wpml_turn_mode_matches_rc_export(configured, csv_path):
    configured.csv_path = csv_path
    b = BuildWaylinesWPML()
    b.setup()
    b.generate()
    placemarks = _placemarks(b.folder)
    last = len(placemarks) - 1

    modes = []
    for i, pm in enumerate(placemarks):
        mode = pm.find("wpml:waypointTurnParam/wpml:waypointTurnMode", NS).text
        modes.append(mode)
        # Only the approach waypoint is exported with useStraightLine=0.
        assert pm.find("wpml:useStraightLine", NS).text == ("0" if i % 4 == 1 else "1")

    # Photo waypoints stop so the camera fires from a standstill; so do the two
    # ends of the wayline, whatever the global turn mode says. Everything else
    # is arced through.
    expected = [
        STOP_TURN if (i % 4 == 2 or i in (0, last)) else "coordinateTurn"
        for i in range(len(placemarks))
    ]
    assert modes == expected


def test_wpml_turn_damping_fits_the_shortest_adjacent_leg(configured, csv_path):
    # A radius wider than half the leg it blends into is rejected in flight with
    # "waypoint turning intercept error (1550)", so each arced waypoint carries a
    # radius sized from its own geometry.
    configured.csv_path = csv_path
    b = BuildWaylinesWPML()
    b.setup()
    b.generate()
    placemarks = _placemarks(b.folder)
    points = [b.placemarkPoint(pm) for pm in placemarks]

    dampings = set()
    for i, pm in enumerate(placemarks):
        mode = pm.find("wpml:waypointTurnParam/wpml:waypointTurnMode", NS).text
        damping = float(pm.find("wpml:waypointTurnParam/wpml:waypointTurnDampingDist", NS).text)
        if mode == STOP_TURN:
            assert damping == 0
            continue
        legs = [
            b.legLength(points[j], points[k])
            for j, k in ((i - 1, i), (i, i + 1))
            if j >= 0 and k < len(points)
        ]
        assert damping == pytest.approx(min(legs) / 3)
        assert damping < min(legs) / 2
        dampings.add(damping)

    # The radii track the legs they sit in, so they are not all the same value.
    assert len(dampings) > 1


# 5 waypoints, so the 5th trips a touch_sky_interval of 5 and adds an apex.
TOUCH_SKY_WPT_ROWS = [
    (i + 1, -74.000 - i * 0.002, 46.0 + i * 0.001, 100 + i, i + 1) for i in range(5)
]
TOUCH_SKY_CPT_ROWS = [(0, -74.001 - i * 0.002, 46.0005 + i * 0.001, 105 + i, 0) for i in range(4)]
TOUCH_SKY_ALTITUDE = 100


def test_touch_sky_apex_is_a_full_stop(configured, tmp_path):
    # The apex sits directly above the waypoint below it, so its two legs double
    # back on each other. Arcing a reversal rounds the corner off and levels the
    # aircraft out below the altitude the climb exists to reach.
    configured.csv_path = write_waypoint_csv(
        tmp_path / "touch_sky.csv", TOUCH_SKY_WPT_ROWS, TOUCH_SKY_CPT_ROWS
    )
    configured.touch_sky = True
    configured.touch_sky_interval = 5
    configured.touch_sky_altitude = TOUCH_SKY_ALTITUDE
    try:
        wpml = BuildWaylinesWPML()
        wpml.setup()
        wpml.generate()
        kml = BuildTemplateKML()
        kml.setup()
        kml.generate()
    finally:
        configured.touch_sky = False

    placemarks = _placemarks(wpml.folder)
    heights = [float(pm.find("wpml:executeHeight", NS).text) for pm in placemarks]
    apex = heights.index(max(heights))
    # The apex is the one waypoint flown to touch_sky_altitude above its checkpoint.
    assert max(heights) == pytest.approx(TOUCH_SKY_CPT_ROWS[-1][3] + TOUCH_SKY_ALTITUDE)

    turn = placemarks[apex].find("wpml:waypointTurnParam", NS)
    assert turn.find("wpml:waypointTurnMode", NS).text == STOP_TURN
    assert turn.find("wpml:waypointTurnDampingDist", NS).text == "0"

    kml_turn = _placemarks(kml.folder)[apex].find("wpml:waypointTurnParam", NS)
    assert kml_turn.find("wpml:waypointTurnMode", NS).text == STOP_TURN


def test_m3e_emits_no_payload_lens_index(configured, csv_path):
    configured.csv_path = csv_path
    configured.drone_model = "m3e"
    for builder in (BuildTemplateKML(), BuildWaylinesWPML()):
        builder.setup()
        builder.generate()
        group = _placemarks(builder.folder)[2].find("wpml:actionGroup", NS)
        # No RC export to compare against for the M3E, so nothing is emitted.
        assert group.findall(".//wpml:payloadLensIndex", NS) == []


# Cardinal legs, so each expected bearing is exact: t1 -> t2 due east, t2 -> t3
# due north, t3 -> t4 due west, t4 -> t5 due south.
HEADING_WPT_ROWS = [
    (1, -74.000, 46.0000, 100, 1),
    (2, -73.998, 46.0000, 101, 2),
    (3, -73.998, 46.0010, 102, 3),
    (4, -74.000, 46.0010, 103, 4),
    (5, -74.000, 46.0005, 104, 5),
]
HEADING_CPT_ROWS = [
    (0, -73.999, 46.0000, 105, 0),
    (0, -73.998, 46.0005, 106, 0),
    (0, -73.999, 46.0010, 107, 0),
    (0, -74.000, 46.0008, 108, 0),
]
# The first waypoint is reached from the take-off site, so it faces the way out
# to the second instead: east, the same as t2's inbound leg.
EXPECTED_ARRIVAL_HEADINGS = ["90", "90", "0", "-90", "180"]


def _oriented_shoots(folder, waypoint_index):
    group = _placemarks(folder)[waypoint_index * 4 + 2].find("wpml:actionGroup", NS)
    return group.findall("wpml:action[wpml:actionActuatorFunc='orientedShoot']", NS)


def _burst_headings(folder, waypoint_count):
    """Every orientedShoot heading, waypoint by waypoint.

    Each shot of one burst fires on the same heading, so a per-waypoint set of
    size 1 is part of the contract.
    """
    headings = []
    for i in range(waypoint_count):
        burst = []
        for shoot in _oriented_shoots(folder, i):
            param = shoot.find("wpml:actionActuatorFuncParam", NS)
            heading = param.find("wpml:aircraftHeading", NS).text
            # DJI requires gimbalYawRotateAngle to track aircraftHeading.
            assert param.find("wpml:gimbalYawRotateAngle", NS).text == heading
            burst.append(heading)
        assert len(set(burst)) == 1
        headings.extend(burst)
    return headings


def test_photo_heading_north_is_the_default(configured, csv_path):
    # The default has to stay byte-identical to the RC export: every burst at 0.
    assert configured.photo_heading == "north"
    configured.csv_path = csv_path
    for builder in (BuildTemplateKML(), BuildWaylinesWPML()):
        builder.setup()
        builder.generate()
        assert _burst_headings(builder.folder, len(WPT_ROWS)) == ["0"] * 2 * len(WPT_ROWS)


def test_photo_heading_arrival_faces_the_inbound_leg(configured, tmp_path):
    # arrival spends no rotation on arrival: the burst is shot on the bearing the
    # aircraft flew in on, so orientedShoot commands a heading it already holds.
    configured.csv_path = write_waypoint_csv(
        tmp_path / "headings.csv", HEADING_WPT_ROWS, HEADING_CPT_ROWS
    )
    configured.photo_heading = "arrival"
    try:
        for builder in (BuildTemplateKML(), BuildWaylinesWPML()):
            builder.setup()
            builder.generate()
            # Two orientedShoot actions per waypoint, both on the same heading.
            expected = [h for h in EXPECTED_ARRIVAL_HEADINGS for _ in range(2)]
            assert _burst_headings(builder.folder, len(HEADING_WPT_ROWS)) == expected
    finally:
        configured.photo_heading = "north"


def test_photo_heading_arrival_leaves_takephoto_alone(configured, tmp_path):
    # takePhoto has no heading field, so the M4E wide shot carries none either.
    configured.csv_path = write_waypoint_csv(
        tmp_path / "headings_m4e.csv", HEADING_WPT_ROWS, HEADING_CPT_ROWS
    )
    configured.photo_heading = "arrival"
    configured.drone_model = "m4e"
    try:
        b = BuildWaylinesWPML()
        b.setup()
        b.generate()
    finally:
        configured.photo_heading = "north"
    group = _placemarks(b.folder)[2].find("wpml:actionGroup", NS)
    photo = group.find("wpml:action[wpml:actionActuatorFunc='takePhoto']", NS)
    param = photo.find("wpml:actionActuatorFuncParam", NS)
    assert param.find("wpml:aircraftHeading", NS) is None
    assert param.find("wpml:gimbalYawRotateAngle", NS) is None


def test_photo_headings_single_waypoint_faces_north(configured):
    # A lone waypoint has no leg to take a bearing from.
    assert photo_headings([("46.0", "-74.0", "100", "1")], "arrival") == ["0"]


def test_photo_heading_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        Config(photo_heading="sideways")


def test_wpml_saved_file_is_wellformed_xml(configured, csv_path, tmp_path):
    configured.csv_path = csv_path
    b = BuildWaylinesWPML()
    b.setup()
    b.generate()
    b.saveNewWPML()
    out = tmp_path / "test_out" / "wpmz" / "waylines.wpml"
    assert out.exists() and out.stat().st_size > 0
    tree = ET.parse(out)  # raises ParseError if malformed
    assert tree.getroot().tag.endswith("}kml")


def test_kml_saved_file_is_wellformed_xml(configured, csv_path, tmp_path):
    configured.csv_path = csv_path
    b = BuildTemplateKML()
    b.setup()
    b.generate()
    b.saveNewKML()
    out = tmp_path / "test_out" / "wpmz" / "template.kml"
    assert out.exists() and out.stat().st_size > 0
    tree = ET.parse(out)
    assert tree.getroot().tag.endswith("}kml")


def test_wpml_setup_rejects_csv_with_no_waypoints(configured, tmp_path):
    """A CSV with no wpt rows must raise a clear error instead of crashing on
    cpt_csv_properties[-1] (IndexError) deep in setup()."""
    empty_csv = write_waypoint_csv(tmp_path / "empty.csv", [], [])
    configured.csv_path = empty_csv
    b = BuildWaylinesWPML()
    with pytest.raises(ValueError, match="No waypoints"):
        b.setup()
