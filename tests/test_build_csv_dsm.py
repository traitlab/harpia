"""DSM-coverage guards in BuildCSV — fail loud instead of flying a bad mission.

Two safety guards:
* a geographic DSM CRS would silently truncate the integer distance matrix to
  zero and yield an arbitrary route;
* a feature/path buffer over DSM nodata yields max=None, which otherwise
  reaches the CSV as "None" and crashes mission generation on float("None").
"""

from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point

from src.lib.build_csv import BuildCSV


def test_geographic_dsm_crs_raises():
    feats = gpd.GeoDataFrame(
        {"point_id": [1, 2]},
        geometry=[Point(-74.0, 45.0), Point(-74.001, 45.001)],
        crs="EPSG:4326",
    )
    dsm = SimpleNamespace(crs=rasterio.crs.CRS.from_epsg(4326))  # geographic
    with pytest.raises(ValueError, match="geographic"):
        BuildCSV("f", "d").align_features_to_dsm(feats, dsm)


def test_missing_dsm_coverage_raises(tmp_path):
    # all-nodata projected DSM; any feature buffer over it -> max=None
    dsm_path = tmp_path / "nodata.tif"
    nodata = -9999.0
    transform = from_origin(500000, 5000000, 1.0, 1.0)  # 1 m pixels, UTM-like
    data = np.full((50, 50), nodata, dtype="float32")
    with rasterio.open(
        dsm_path,
        "w",
        driver="GTiff",
        height=50,
        width=50,
        count=1,
        dtype="float32",
        crs="EPSG:32618",
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(data, 1)

    feats = gpd.GeoDataFrame(
        {"point_id": [7]},
        geometry=[Point(500025, 4999975)],  # inside the raster
        crs="EPSG:32618",
    )
    bc = BuildCSV("f", str(dsm_path), buffer_feature=3)
    with pytest.raises(ValueError, match="no data"):
        bc.extract_features_elevations(feats)
