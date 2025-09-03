from pathlib import Path
from typing import Optional, List

from pydantic import BaseModel, Field, FilePath, field_validator
from typing_extensions import Annotated

PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

class Config(BaseModel):
    csv_path: Optional[FilePath] = None

    features_path: Optional[FilePath] = None
    dsm_path: Optional[str] = None

    output_folder: Optional[Path] = None
    output_filename: Optional[str] = None

    buffer: int = 6
    approach: int = 10

    buffer_path: Optional[int] = 10
    buffer_feature: Optional[int] = 3
    takeoff_coords: Optional[List[float]] = None
    takeoff_coords_projected: bool = False

    aoi_path: Optional[FilePath] = None
    aoi_index: Optional[int] = None
    aoi_qualifier: Optional[str] = None

    touch_sky: bool = False
    touch_sky_interval: Optional[int] = 10
    touch_sky_altitude: Optional[int] = 100

    debug_mode: bool = False

    kml_model_file_path: FilePath = Path(f"{PROJECT_ROOT}/templates/onewpt-wpmz/template.kml")
    output_kml_file_path: Path = 'wpmz/template.kml'
    wpml_model_file_path: FilePath = Path(f"{PROJECT_ROOT}/templates/onewpt-wpmz/waylines.wpml")
    output_wpml_file_path: Path = 'wpmz/waylines.wpml'

    class Config:
        arbitrary_types_allowed = True
