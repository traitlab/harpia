import re
from pathlib import Path
from typing import Optional, List

from pydantic import BaseModel, Field, FilePath, field_validator
from typing_extensions import Annotated


class Config(BaseModel):
    approach: int = 10
    buffer: int = 6

    csv_path: Optional[FilePath] = None

    touch_sky: bool = False
    touch_sky_interval: Optional[int] = 10
    touch_sky_altitude: Optional[int] = 100

    kml_model_file_path: FilePath = './templates/onewpt-wpmz/template.kml'
    output_kml_file_path: Path = 'wpmz/template.kml'
    wpml_model_file_path: FilePath = './templates/onewpt-wpmz/waylines.wpml'
    output_wpml_file_path: Path = 'wpmz/waylines.wpml'

    features_path: Optional[FilePath] = None
    dsm_path: Optional[FilePath] = None
    aoi_path: Optional[FilePath] = None
    aoi_index: Optional[int]
    aoi_qualifier: Optional[str]
    buffer_path: Optional[int] = 10
    buffer_tree: Optional[int] = 3
    takeoff_coords: Optional[List[float]] = None
    takeoff_coords_projected: bool = False  # Default: WGS84 coordinates

    output_folder: Optional[Path] = None
    output_filename: Optional[str] = None

    debug_mode: bool = False

    class Config:
        arbitrary_types_allowed = True
