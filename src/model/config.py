from pathlib import Path

from pydantic import BaseModel, FilePath, field_validator

PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

# Drone model configurations
DRONE_MODEL_CONFIG = {
    "m3e": {
        "oriented_camera_type": "66",
        "photo_actions": [
            {
                "focal_length": "168",
                "suffix": "tele",
                "uuid": "703556e4-81fb-4294-b607-05d5f748377f",
            },
            {
                "focal_length": "24",
                "suffix": "wide",
                "uuid": "51ae7825-56de-41d3-90bb-3c9ed6de7960",
            },
        ],
    },
    "m4e": {
        "oriented_camera_type": "88",
        "photo_actions": [
            {
                "focal_length": "168",
                "suffix": "tele",
                "uuid": "703556e4-81fb-4294-b607-05d5f748377f",
            },
            {"focal_length": "72", "suffix": "med", "uuid": "4972910c-8c61-4576-90f7-a9e07d560854"},
            {
                "focal_length": "24",
                "suffix": "wide",
                "uuid": "51ae7825-56de-41d3-90bb-3c9ed6de7960",
            },
        ],
    },
}


class Config(BaseModel):
    csv_path: FilePath | None = None

    features_path: FilePath | None = None
    dsm_path: str | None = None

    drone_model: str = "m3e"

    output_folder: Path | None = None
    output_filename: str | None = None

    buffer: int = 6
    approach: int = 10

    buffer_path: int | None = 10
    buffer_feature: int | None = 3
    takeoff_coords: list[float] | None = None
    takeoff_coords_projected: bool = False

    aoi_path: FilePath | None = None
    aoi_index: int | None = None
    aoi_qualifier: str | None = None

    touch_sky: bool = False
    touch_sky_interval: int | None = 10
    touch_sky_altitude: int | None = 100

    debug_mode: bool = False

    output_kml_file_path: Path = Path("wpmz/template.kml")
    output_wpml_file_path: Path = Path("wpmz/waylines.wpml")

    @field_validator("drone_model")
    @classmethod
    def validate_drone_model(cls, v):
        if v.lower() not in DRONE_MODEL_CONFIG:
            supported_models = ", ".join(DRONE_MODEL_CONFIG.keys())
            raise ValueError(f"drone_model must be one of: {supported_models}")
        return v.lower()

    @property
    def kml_model_file_path(self) -> Path:
        return Path(f"{PROJECT_ROOT}/templates/{self.drone_model}-onewpt-wpmz/template.kml")

    @property
    def wpml_model_file_path(self) -> Path:
        return Path(f"{PROJECT_ROOT}/templates/{self.drone_model}-onewpt-wpmz/waylines.wpml")

    class Config:
        arbitrary_types_allowed = True
