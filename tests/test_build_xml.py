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

from src.lib.build_template_kml import BuildTemplateKML
from src.lib.build_waylines_wpml import BuildWaylinesWPML

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
    # waypointSpeed reflects the configured global speed (15) for fly-through pts.
    assert first.find("wpml:waypointSpeed", NS).text == b.waypointSpeed
    # indices run 0..N-1 contiguously across all placemarks.
    indices = [int(p.find("wpml:index", NS).text) for p in placemarks]
    assert indices == list(range(len(placemarks)))


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


def test_kml_m4e_has_three_photo_actions(configured, csv_path):
    configured.csv_path = csv_path
    configured.drone_model = "m4e"
    b = BuildTemplateKML()
    b.setup()
    b.generate()
    photos_pm = _placemarks(b.folder)[2]
    shoots = photos_pm.findall(
        "wpml:actionGroup/wpml:action[wpml:actionActuatorFunc='orientedShoot']", NS
    )
    assert len(shoots) == 3  # m4e: tele + med + wide


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
