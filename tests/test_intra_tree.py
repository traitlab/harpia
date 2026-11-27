"""Tests for intra-tree mode: several photo points on one crown.

Between two consecutive points of the same crown, the drone flies at the max
DSM of a narrow corridor plus buffer, with no approach height and no approach
waypoint, and the route visits all points of a crown in a row.
"""

import xml.etree.ElementTree as ET

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from conftest import CSV_HEADER
from rasterio.transform import from_origin
from shapely.geometry import Point

from src.lib.build_csv import BuildCSV
from src.lib.build_template_kml import BuildTemplateKML
from src.lib.build_waylines_wpml import BuildWaylinesWPML
from src.lib.placemark_plan import (
    APPROACH,
    FIRST,
    INTRA_CLIMB,
    INTRA_DESCENT,
    LAST,
    PHOTO,
    TOUCH_SKY,
    placemark_plan,
    read_crown_ids,
    step_height,
)

NS = {
    "kml": "http://www.opengis.net/kml/2.2",
    "wpml": "http://www.dji.com/wpmz/1.0.6",
}
CRS = "EPSG:32618"


# -----------------------------------------------------------------------------
# Placemark plan
# -----------------------------------------------------------------------------
def _props(elevations):
    return [("46.0", "-74.0", str(e), str(i + 1)) for i, e in enumerate(elevations)]


def _cpts(elevations):
    # One per leg plus a copy at each end, as the builders' setup() lays them out.
    cpts = _props(elevations)
    return [cpts[0], *cpts, cpts[-1]]


def test_plan_without_crowns_is_unchanged():
    wpts, cpts = _props([100, 110, 112]), _cpts([105, 108])
    assert placemark_plan(wpts, cpts, 6, 10) == placemark_plan(
        wpts, cpts, 6, 10, crown_ids=[None, None, None]
    )


def test_plan_intra_tree_drops_approach_and_transit_height():
    wpts, cpts = _props([100, 102, 120]), _cpts([104, 125])
    steps = placemark_plan(wpts, cpts, 6, 10, crown_ids=["A", "A", None])
    assert [s.kind for s in steps] == [
        FIRST,
        APPROACH,
        PHOTO,
        INTRA_CLIMB,
        INTRA_DESCENT,
        PHOTO,
        LAST,
        FIRST,
        APPROACH,
        PHOTO,
        LAST,
    ]
    climb, descent = steps[3], steps[4]
    # cpt + buffer only: no approach height inside the crown.
    assert step_height(climb.elevation, climb.offsets) == "110.0"
    assert step_height(descent.elevation, descent.offsets) == "110.0"
    assert (climb.wpt, descent.wpt) == (0, 1)
    assert climb.gimbal == descent.gimbal == "-90"


def test_plan_drops_intra_placemarks_level_with_the_photo():
    # The checkpoint equals the first photo's elevation: no climb at A.
    steps = placemark_plan(_props([104, 100]), _cpts([104]), 6, 10, crown_ids=["A", "A"])
    assert [s.kind for s in steps] == [FIRST, APPROACH, PHOTO, INTRA_DESCENT, PHOTO, LAST]
    # Both photos at the checkpoint's elevation: straight across.
    steps = placemark_plan(_props([104, 104]), _cpts([104]), 6, 10, crown_ids=["A", "A"])
    assert [s.kind for s in steps] == [FIRST, APPROACH, PHOTO, PHOTO, LAST]


def test_plan_touch_sky_waits_until_the_crown_is_left():
    wpts, cpts = _props([100, 100, 100, 100]), _cpts([105, 105, 105])
    steps = placemark_plan(
        wpts,
        cpts,
        6,
        10,
        touch_sky=True,
        touch_sky_interval=1,
        crown_ids=["A", "A", "A", None],
    )
    touch = [s.wpt for s in steps if s.kind == TOUCH_SKY]
    # Due after waypoint 0, but deferred to the crown's last point.
    assert touch == [2, 3]


def test_plan_different_crowns_are_not_intra_tree():
    steps = placemark_plan(_props([100, 100]), _cpts([105]), 6, 10, crown_ids=["A", "B"])
    assert INTRA_CLIMB not in [s.kind for s in steps]


def test_read_crown_ids(tmp_path):
    csv = tmp_path / "w.csv"
    csv.write_text(
        "point_id,cluster_id,crown_id,type,lon_x,lat_y,elevation_from_dsm,order\n"
        "1,0,A,wpt,-74,46,100,1\n0,0,A,cpt,-74,46,104,0\n"
        "2,0,A,wpt,-74,46,100,2\n0,0,,cpt,-74,46,110,0\n"
        "3,0,,wpt,-74,46,100,3\n"
    )
    assert read_crown_ids(csv, 3) == ["A", "A", None]


def test_read_crown_ids_without_column(tmp_path):
    csv = tmp_path / "w.csv"
    csv.write_text(
        CSV_HEADER + "1,0,wpt,-74,46,100,1\n0,0,cpt,-74,46,104,0\n2,0,wpt,-74,46,100,2\n"
    )
    assert read_crown_ids(csv, 2) == [None, None]


# -----------------------------------------------------------------------------
# Route: points of a crown in a row
# -----------------------------------------------------------------------------
def _matrix(coords):
    pts = [Point(c) for c in coords]
    return BuildCSV("f", "d").build_distance_matrix(pts)


def _contiguous(route, groups):
    order = [groups[n] for n in route if groups[n] is not None]
    runs = [g for i, g in enumerate(order) if i == 0 or order[i - 1] != g]
    return len(runs) == len(set(runs))


def test_tsp_keeps_crowns_together():
    # Interleaved on a line: the shortest route alternates crowns A and B.
    coords = [(0, 0), (10, 0), (20, 0), (30, 0), (40, 0), (50, 0)]
    groups = ["A", "B", "A", "B", "A", "B"]
    route = BuildCSV.solve_tsp_ortools(_matrix(coords), time_limit_seconds=1, groups=groups)
    assert sorted(route) == list(range(len(coords)))
    assert _contiguous(route, groups)


def test_tsp_does_not_split_the_start_crown():
    # Starting from a point in the middle of crown A, a closed tour could leave
    # half of A for the end of the route.
    coords = [(0, 0), (-1, 0), (1, 0), (50, 0), (51, 0), (-50, 0)]
    groups = ["A", "A", "A", None, None, None]
    route = BuildCSV.solve_tsp_ortools(
        _matrix(coords),
        takeoff_coords=(0, 0),
        waypoints_coords=np.array(coords),
        time_limit_seconds=1,
        groups=groups,
    )
    assert route[0] == 0
    assert set(route[:3]) == {0, 1, 2}


def test_check_groups_contiguous_raises():
    with pytest.raises(ValueError, match="more than one pass"):
        BuildCSV.check_groups_contiguous([0, 1, 2], ["A", "B", "A"])
    BuildCSV.check_groups_contiguous([0, 1, 2, 3], ["A", "A", None, "B"])


# -----------------------------------------------------------------------------
# Crowns and checkpoints, on a synthetic DSM
# -----------------------------------------------------------------------------
X0, Y0, RES, N = 600000.0, 5000000.0, 0.5, 200
CROWN_A = (X0 + 40, Y0 - 50)


@pytest.fixture
def dsm_path(tmp_path):
    """Flat ground at 100 m, crown A (130 m) and a taller neighbour 14 m east (150 m)."""
    xs = X0 + (np.arange(N) + 0.5) * RES
    ys = Y0 - (np.arange(N) + 0.5) * RES
    x, y = np.meshgrid(xs, ys)
    dsm = np.full((N, N), 100.0)
    for cx, cy, r, h in [(*CROWN_A, 8, 130), (CROWN_A[0] + 14, CROWN_A[1], 5, 150)]:
        d = np.hypot(x - cx, y - cy)
        dsm = np.maximum(dsm, np.where(d < r, h - (d / r) * 10, 0))
    path = tmp_path / "dsm.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=N,
        width=N,
        count=1,
        dtype="float32",
        crs=CRS,
        transform=from_origin(X0, Y0, RES, RES),
    ) as dst:
        dst.write(dsm.astype("float32"), 1)
    return str(path)


def _write_crowns(tmp_path, geometries, crown_ids=None):
    data = {} if crown_ids is None else {"crown_id": crown_ids}
    path = tmp_path / "site_crowns.gpkg"
    gpd.GeoDataFrame(data, geometry=geometries, crs=CRS).to_file(path)
    return str(path)


def _points(coords):
    return gpd.GeoDataFrame(
        {"point_id": list(range(1, len(coords) + 1))},
        geometry=[Point(c) for c in coords],
        crs=CRS,
    )


def test_assign_crowns(tmp_path):
    crowns = _write_crowns(tmp_path, [Point(0, 0).buffer(5), Point(20, 0).buffer(5)], ["A", "B"])
    points = _points([(1, 0), (21, 0), (50, 0)])
    out = BuildCSV("f", "d", crowns_path=crowns).assign_crowns(points)
    assert out["crown_id"].tolist() == ["A", "B", None]


def test_assign_crowns_falls_back_to_fid(tmp_path):
    crowns = _write_crowns(tmp_path, [Point(0, 0).buffer(5), Point(20, 0).buffer(5)])
    out = BuildCSV("f", "d", crowns_path=crowns).assign_crowns(_points([(1, 0), (21, 0)]))
    # GeoPackage FIDs start at 1.
    assert out["crown_id"].tolist() == [1, 2]


def test_assign_crowns_overlap_raises(tmp_path):
    crowns = _write_crowns(tmp_path, [Point(0, 0).buffer(5), Point(4, 0).buffer(5)], ["A", "B"])
    with pytest.raises(ValueError, match="more than one crown"):
        BuildCSV("f", "d", crowns_path=crowns).assign_crowns(_points([(2, 0), (20, 0)]))


def test_duplicate_crown_ids_raise(tmp_path):
    crowns = _write_crowns(tmp_path, [Point(0, 0).buffer(5), Point(20, 0).buffer(5)], ["A", "A"])
    with pytest.raises(ValueError, match="unique"):
        BuildCSV("f", "d", crowns_path=crowns).assign_crowns(_points([(1, 0), (21, 0)]))


def test_crowns_need_point_features(tmp_path):
    features = tmp_path / "site_polygons.gpkg"
    gpd.GeoDataFrame(geometry=[Point(0, 0).buffer(2), Point(9, 0).buffer(2)], crs=CRS).to_file(
        features
    )
    crowns = _write_crowns(tmp_path, [Point(0, 0).buffer(5)], ["A"])
    with pytest.raises(ValueError, match="needs point features"):
        BuildCSV(str(features), "d", crowns_path=crowns).read_features()


def test_intra_tree_checkpoint_ignores_the_taller_neighbour(dsm_path):
    # Two points on crown A, 4 m either side of its centre. The 10 m transit
    # corridor reaches the 150 m neighbour; the 3 m intra-tree one does not.
    coords = [(CROWN_A[0] - 4, CROWN_A[1]), (CROWN_A[0] + 4, CROWN_A[1])]
    bc = BuildCSV("f", dsm_path, buffer_path=10, buffer_feature=3, intra_tree_buffer_path=3)
    features = bc.extract_features_elevations(_points(coords))

    transit = bc.extract_path_checkpoints(bc.get_tsp_solution_df(features, [0, 1]))
    features["crown_id"] = ["A", "A"]
    intra = bc.extract_path_checkpoints(bc.get_tsp_solution_df(features, [0, 1]))

    assert transit["elev"].iloc[0] > 140
    assert intra["elev"].iloc[0] < 131
    assert intra["elev"].iloc[0] >= features["elev"].max()
    assert intra["crown_id"].iloc[0] == "A"


def test_fix_elevation_leaves_intra_tree_checkpoints_alone():
    df = pd.DataFrame(
        [
            {"type": "wpt", "elev": 110.0, "crown_id": "A"},
            {"type": "cpt", "elev": 110.0, "crown_id": "A"},
            {"type": "wpt", "elev": 110.0, "crown_id": "A"},
            {"type": "cpt", "elev": 120.0, "crown_id": None},
            {"type": "wpt", "elev": 120.0, "crown_id": None},
        ]
    )
    fixed = BuildCSV("f", "d").fix_cpt_wpt_elevation_duplicates(df)
    assert fixed["elev"].tolist() == [110.0, 110.0, 110.0, 121.0, 120.0]


def test_run_writes_crown_id(tmp_path, dsm_path):
    features = tmp_path / "site_points.gpkg"
    coords = [
        (CROWN_A[0] - 4, CROWN_A[1]),
        (X0 + 80, Y0 - 80),
        (CROWN_A[0] + 4, CROWN_A[1]),
        (CROWN_A[0], CROWN_A[1] - 5),
    ]
    _points(coords).to_file(features)
    crowns = _write_crowns(tmp_path, [Point(CROWN_A).buffer(8)], ["A"])

    bc = BuildCSV(str(features), dsm_path, crowns_path=crowns, tsp_time_limit_seconds=1)
    gpkg, csv, _ = bc.run(tmp_path / "out", "site_wpt")

    assert "crown_id" in csv.columns
    assert "crown_id" in gpkg.columns
    wpts = csv[csv["type"] == "wpt"]
    assert sorted(wpts["crown_id"].dropna().tolist()) == ["A", "A", "A"]
    groups = [None if pd.isna(c) else c for c in wpts["crown_id"]]
    assert _contiguous(list(range(len(groups))), groups)


def test_run_without_crowns_writes_no_crown_id(tmp_path, dsm_path):
    features = tmp_path / "site_points.gpkg"
    _points([(CROWN_A[0] - 4, CROWN_A[1]), (X0 + 80, Y0 - 80)]).to_file(features)
    gpkg, csv, _ = BuildCSV(str(features), dsm_path, tsp_time_limit_seconds=1).run(
        tmp_path / "out", "site_wpt"
    )
    assert "crown_id" not in csv.columns
    assert "crown_id" not in gpkg.columns


# -----------------------------------------------------------------------------
# Mission files
# -----------------------------------------------------------------------------
@pytest.fixture
def intra_csv(tmp_path):
    path = tmp_path / "site_points.csv"
    path.write_text(
        "point_id,cluster_id,crown_id,type,lon_x,lat_y,elevation_from_dsm,order\n"
        "1,0,A,wpt,-74.00000,46.00000,128,1\n"
        "0,0,A,cpt,-74.00003,46.00000,130,0\n"
        "2,0,A,wpt,-74.00006,46.00000,127,2\n"
        "0,0,,cpt,-74.00050,46.00000,150,0\n"
        "3,0,,wpt,-74.00100,46.00000,118,3\n"
    )
    return path


def _placemarks(builder):
    return builder.folder.findall("kml:Placemark", NS)


def test_wpml_intra_tree_sequence(configured, intra_csv):
    configured.csv_path = intra_csv
    b = BuildWaylinesWPML()
    b.setup()
    b.generate()
    placemarks = _placemarks(b)
    # Waypoint 1: first, approach, photo, climb. Waypoint 2: descent, photo,
    # last. Waypoint 3: the usual four.
    assert len(placemarks) == 11
    heights = [float(p.find("wpml:executeHeight", NS).text) for p in placemarks]
    assert heights[3] == heights[4] == 130 + configured.buffer
    speeds = [p.find("wpml:waypointSpeed", NS).text for p in placemarks]
    assert speeds[4] == "3"
    assert speeds[3] == b.waypointSpeed
    indices = [int(p.find("wpml:index", NS).text) for p in placemarks]
    assert indices == list(range(len(placemarks)))
    group_ids = [int(g.text) for g in b.folder.findall(".//wpml:actionGroupId", NS)]
    assert group_ids == list(range(len(group_ids)))


def test_kml_intra_tree_descent_states_its_speed(configured, intra_csv):
    configured.csv_path = intra_csv
    b = BuildTemplateKML()
    b.setup()
    b.generate()
    placemarks = _placemarks(b)
    assert len(placemarks) == 11
    descent = placemarks[4]
    assert descent.find("wpml:waypointSpeed", NS).text == "3"
    assert descent.find("wpml:useGlobalSpeed", NS) is None
    assert placemarks[3].find("wpml:useGlobalSpeed", NS).text == "1"
    root = ET.fromstring(ET.tostring(b.root))
    assert len(root.findall(".//kml:Folder/kml:Placemark", NS)) == 11
