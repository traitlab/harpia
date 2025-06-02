import re
from pathlib import Path

from pydantic import BaseModel, Field, FilePath, field_validator
from typing_extensions import Annotated


class Config(BaseModel):
    approach: int
    buffer: int

    base_path: Path
    base_name: str

    points_csv_file_path: FilePath

    touch_sky: bool
    touch_sky_interval: int
    touch_sky_altitude: float

    kml_model_file_path: FilePath = './scripts/wpml/model/onewpt-Remote.kmz.org/wpmz/template.kml'
    output_kml_file_path: Path = 'wpmz/template.kml'
    wpml_model_file_path: FilePath = './scripts/wpml/model/onewpt-Remote.kmz.org/wpmz/waylines.wpml'
    output_wpml_file_path: Path = 'wpmz/waylines.wpml'


    debug_mode: bool = False

    class Config:
        arbitrary_types_allowed = True
