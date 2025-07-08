import importlib
import lib.build_csv
importlib.reload(lib.build_csv)
from lib.build_csv import BuildCSV

# Set your file paths and parameters
features_path = "D:/test_harpia/test_buildCSV/carpotroche_centroids.gpkg"
dsm_path = "D:/test_harpia/test_buildCSV/20250520_tbscarpotroche_m3e_dsm.cog.tif"
aoi_path = None  # or provide a path if you want to test AOI filtering

# def main():
builder = BuildCSV(
    features_path=features_path,
    dsm_path=dsm_path,
    epsg_code=32718,
    # aoi_path=aoi_path,
    # aoi_index=1,
    # aoi_qualifier="",
    # aoi_relation="",
    # buffer_path=10,
    # buffer_tree=3
)

builder.run(output_folder = 'D:/test_harpia/test_buildCSV/fromPython')