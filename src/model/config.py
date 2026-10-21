from pathlib import Path

from pydantic import BaseModel, ConfigDict, FilePath, field_validator

PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

# The M4E and the M4D fly the same three-shot sequence; only their camera and
# payload enum values differ. The list is read-only, so both models share it.
M4_PHOTO_ACTIONS = [
    {
        "focal_length": "168",
        "suffix": "tele",
        "uuid": "703556e4-81fb-4294-b607-05d5f748377f",
    },
    {
        "focal_length": "72",
        "suffix": "med",
        "uuid": "4972910c-8c61-4576-90f7-a9e07d560854",
    },
    # 1x shot via takePhoto (wide): orientedShoot fires the zoom camera,
    # which has no DJI Time Sync and so no RTK-accurate position.
    {
        "actuator_func": "takePhoto",
        "suffix": "wide",
    },
]

# Drone model configurations.
#
# kml_payload_lens_index / wpml_payload_lens_index: the payloadLensIndex the
# remote controller writes into template.kml and waylines.wpml for that payload,
# or None when it writes none. "visable" is DJI's own spelling. The M4E omits it
# from template.kml; the M4D writes it in both files.
DRONE_MODEL_CONFIG = {
    "m3e": {
        "oriented_camera_type": "66",
        "kml_payload_lens_index": None,
        "wpml_payload_lens_index": None,
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
        "kml_payload_lens_index": None,
        "wpml_payload_lens_index": "visable",
        "photo_actions": M4_PHOTO_ACTIONS,
    },
    "m4d": {
        "oriented_camera_type": "98",
        "kml_payload_lens_index": "visable",
        "wpml_payload_lens_index": "visable",
        "photo_actions": M4_PHOTO_ACTIONS,
    },
}

# Aircraft yaw for a waypoint's photo burst.
#
# north: rotate to true north before shooting, so frames of the same tree line up
#        across missions. arrival: keep the heading the aircraft flew in with,
#        which saves a rotation at every waypoint. See src/lib/photo_heading.py.
PHOTO_HEADING_MODES = ("north", "arrival")


class Config(BaseModel):
    csv_path: FilePath | None = None

    features_path: FilePath | None = None
    dsm_path: str | None = None

    drone_model: str = "m3e"

    photo_heading: str = "north"

    output_folder: Path | None = None
    output_filename: str | None = None

    buffer: int = 6
    approach: int = 10

    buffer_path: int | None = 10
    buffer_feature: int | None = 3
    takeoff_coords: list[float] | None = None
    takeoff_coords_projected: bool = False

    # Wall-clock budget for the OR-Tools TSP solver. Larger surveys may need
    # more than the 30 s default to converge on a good route.
    tsp_time_limit_seconds: int = 30

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

    @field_validator("photo_heading")
    @classmethod
    def validate_photo_heading(cls, v):
        if v.lower() not in PHOTO_HEADING_MODES:
            supported_modes = ", ".join(PHOTO_HEADING_MODES)
            raise ValueError(f"photo_heading must be one of: {supported_modes}")
        return v.lower()

    @property
    def kml_model_file_path(self) -> Path:
        return Path(f"{PROJECT_ROOT}/templates/{self.drone_model}-onewpt-wpmz/template.kml")

    @property
    def wpml_model_file_path(self) -> Path:
        return Path(f"{PROJECT_ROOT}/templates/{self.drone_model}-onewpt-wpmz/waylines.wpml")

    model_config = ConfigDict(arbitrary_types_allowed=True)
