"""Tests for the deterministic route-planning units in ``BuildCSV``.

``solve_tsp_ortools`` (src/lib/build_csv.py:223) and ``build_distance_matrix``
(src/lib/build_csv.py:185) are pure/static and testable without GIS data.
``get_tsp_solution_df`` (src/lib/build_csv.py:272) reorders features by route.

The full ``BuildCSV.run`` pipeline requires a real DSM raster + features layer
and is NOT covered here (see module-level note in the suite report).
"""

import numpy as np
import pytest
from shapely.geometry import Point

from src.lib.build_csv import BuildCSV


def _euclidean_matrix(coords):
    n = len(coords)
    dm = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            dm[i, j] = np.linalg.norm(np.array(coords[i]) - np.array(coords[j]))
    return dm


def _route_length(route, dm):
    return sum(dm[route[k], route[k + 1]] for k in range(len(route) - 1))


def test_build_distance_matrix_symmetric_zero_diagonal():
    pts = [Point(0, 0), Point(3, 0), Point(3, 4)]
    dm = BuildCSV("f", "d").build_distance_matrix(pts)
    assert dm.shape == (3, 3)
    assert np.allclose(np.diag(dm), 0.0)
    assert np.allclose(dm, dm.T)
    # 3-4-5 triangle distances
    assert dm[0, 1] == pytest.approx(3.0)
    assert dm[0, 2] == pytest.approx(5.0)
    assert dm[1, 2] == pytest.approx(4.0)


def test_tsp_visits_every_point_once():
    coords = [(0, 0), (0, 1), (1, 1), (1, 0), (2, 2)]
    route = BuildCSV.solve_tsp_ortools(_euclidean_matrix(coords))
    assert route is not None
    assert sorted(route) == list(range(len(coords)))  # each node exactly once


def test_tsp_square_is_optimal_perimeter():
    # 4 points on a unit square: optimal open path is the perimeter, length 3.0
    # (OR-Tools returns an open route, not a closed tour).
    square = [(0, 0), (0, 1), (1, 1), (1, 0)]
    dm = _euclidean_matrix(square)
    route = BuildCSV.solve_tsp_ortools(dm)
    assert route is not None
    assert sorted(route) == [0, 1, 2, 3]
    assert route[0] == 0  # default start_index
    length = _route_length(route, dm)
    assert length == pytest.approx(3.0, abs=1e-6)
    assert np.isfinite(length)


def test_tsp_deterministic_same_input_same_route():
    coords = [(0, 0), (0, 1), (1, 1), (1, 0), (5, 5), (5, 4)]
    dm = _euclidean_matrix(coords)
    r1 = BuildCSV.solve_tsp_ortools(dm)
    r2 = BuildCSV.solve_tsp_ortools(dm)
    assert r1 == r2


def test_tsp_start_index_follows_nearest_to_takeoff():
    # takeoff sits next to node 3 -> route must start at node 3.
    coords = np.array([(0, 0), (0, 10), (10, 10), (10, 0)], float)
    dm = _euclidean_matrix(coords)
    takeoff = [11.0, 0.0]  # closest to (10, 0) == node 3
    route = BuildCSV.solve_tsp_ortools(dm, takeoff_coords=takeoff, waypoints_coords=coords)
    assert route is not None
    assert route[0] == 3
    assert sorted(route) == [0, 1, 2, 3]


def test_get_tsp_solution_df_reorders_and_labels():
    gpd = pytest.importorskip("geopandas")
    feats = gpd.GeoDataFrame(
        {"point_id": [10, 20, 30], "elev": [1.0, 2.0, 3.0]},
        geometry=[Point(0, 0), Point(1, 1), Point(2, 2)],
        crs="EPSG:4326",
    )
    route = [2, 0, 1]
    out = BuildCSV("f", "d").get_tsp_solution_df(feats, route)
    assert list(out.columns) == ["point_id", "type", "geometry", "elev", "order"]
    assert list(out["point_id"]) == [30, 10, 20]  # reordered by route
    assert list(out["order"]) == [1, 2, 3]
    assert set(out["type"]) == {"wpt"}
