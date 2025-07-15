import re
from pathlib import Path
from typing import Optional, List

from pydantic import BaseModel, Field, FilePath, field_validator
from typing_extensions import Annotated


class Config(BaseModel):
    approach: int
    buffer: int

    base_path: Path
    base_name: str

    points_csv_file_path: Optional[FilePath] = None

    touch_sky: bool
    touch_sky_interval: int
    touch_sky_altitude: float

    kml_model_file_path: FilePath = './scripts/model/onewpt-wpmz/template.kml'
    output_kml_file_path: Path = 'wpmz/template.kml'
    wpml_model_file_path: FilePath = './scripts/model/onewpt-wpmz/waylines.wpml'
    output_wpml_file_path: Path = 'wpmz/waylines.wpml'

    features_path: Optional[str] = None
    dsm_path: Optional[str] = None
    aoi_path: Optional[str] = None
    aoi_index: Optional[int] = 1
    aoi_qualifier: Optional[str] = ""
    buffer_path: Optional[int] = 10
    buffer_tree: Optional[int] = 3
    takeoff_site_coords: Optional[List[float]] = None
    output_folder: Optional[str] = None
    output_filename: Optional[str] = None

    debug_mode: bool = False

    class Config:
        arbitrary_types_allowed = True
