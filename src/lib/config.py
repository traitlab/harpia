import argparse
import os
import re
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from src.model.config import Config


# -----------------------------------------------------------------------------
def load_config(config_path: str) -> Config:
    # Load the configuration file
    if os.path.exists(config_path):
        with open(config_path, 'r') as file:
            config_data = yaml.safe_load(file)
        return Config(**config_data)
    else:
        print(f"Configuration file not found: {config_path}")
        sys.exit(1)


# Parse command line arguments
parser = argparse.ArgumentParser(
    description='Generate drone mission files (KMZ) from features layer or existing waypoint coordinates. Supports automatic waypoint mission generation from GeoPackage/Shapefile + DSM, or direct processing of CSV waypoints.')
# Input/Output Settings
parser.add_argument('--config', '-c', type=str, required=False,
                    help='Path to the configuration file. Other choice is to provide the --csv or --features arguments.')
parser.add_argument('--csv', '-csv', type=str, required=False,
                    help='Path to the input CSV file in the right format containing waypoints. If not provided, it will be generated from features.')
parser.add_argument('--features', '-f', type=str, required=False,
                    help='Path to the input features file (e.g., GeoPackage, Shapefile).')
parser.add_argument('--dsm', '-dsm', type=str, required=False,
                    help='Path to the DSM raster file.')

parser.add_argument('--output-path', '-op', type=str, required=False,
                    help='Custom output directory path (default: same directory as input file)')
parser.add_argument('--output-filename', '-of', type=str, required=False,
                    help='Custom output filename without extension (default: same as input file). ')

# Waypoint Generation Settings
parser.add_argument('--aoi', '-aoi', type=str, required=False,
                    help='Path to the AOI file to filter features.')
parser.add_argument('--aoi-index', '-i', type=int,
                    help='Index of the AOI polygon to use.')
parser.add_argument('--aoi-qualifier', '-q', type=str,
                    help='Qualifier for the AOI to be used in output filenames.')
parser.add_argument('--takeoff-coords', '-to', type=float, nargs=2,
                    metavar=('X', 'Y'), required=False,
                    help='Coordinates (x, y) for projected CRS or (lat, lon) for WGS84.')
parser.add_argument('--takeoff-coords-projected', '-proj', action='store_true', default=False,
                    help='Flag to indicate takeoff coordinates are in projected CRS (default: False (WGS84))')

# Touch-sky Settings
parser.add_argument('--touch-sky', '-ts', action='store_true', default=False,
                    help='Enable touch-sky feature where drone flies up periodically (default: False)')
parser.add_argument('--touch-sky-interval', '-n', type=int, default=10,
                    help='Number of features between each touch-sky action (default: 10, min: 5)')
parser.add_argument('--touch-sky-altitude', '-alt', type=int, default=100,
                    help='Altitude in meters above DSM for touch-sky action (default: 100, min: 16, max: 200)')

parser.add_argument('--debug', '-d', action='store_true',
                    help='Run in debug mode (default: False)')

args = parser.parse_args()

# Validate that either --config or --csv or --features is provided
if not args.config and not args.csv and not args.features:
    parser.error("Either --config, --csv or --features must be provided")

# Validate that only one of --config, --csv or --features is provided
if args.config and (args.csv or args.features):
    parser.error("Cannot use --config with --csv or --features")

if args.csv and args.features:
    parser.error("Cannot use both --csv and --features")

# Validate touch-sky parameters
if args.touch_sky:
    if args.touch_sky_interval < 5:
        parser.error("--touch-sky-interval must be at least 5")
    if args.touch_sky_altitude > 200:
        parser.error("--touch-sky-altitude cannot exceed 200 meters")
    if args.touch_sky_altitude < 16:
        parser.error("--touch-sky-altitude cannot be less than 16 meters")

# Validate BuildCSV parameters
if args.features and not args.dsm:
    parser.error("--dsm must be provided when --features is specified")

if (args.aoi_index or args.aoi_qualifier) and not args.aoi:
    parser.error("--aoi must be provided when --aoi-index or --aoi-qualifier is specified")

if args.aoi_index and not args.aoi_qualifier:
    parser.error("--aoi-index requires --aoi-qualifier to be specified")

if args.aoi_qualifier and not args.aoi_index:
    parser.error("--aoi-qualifier requires --aoi-index to be specified")

if args.takeoff_coords_projected and not args.takeoff_coords:
    parser.error("--takeoff-coords must be provided when --takeoff-coords-projected is True")

try:
    # Create config object
    if args.config:
        config = load_config(args.config)
    
    else:
        # Create a default Config object with command line values
        config = Config(
            # BuildCSV parameters
            features_path=args.features,
            dsm_path=args.dsm,
            aoi_path=args.aoi,
            aoi_index=args.aoi_index,
            aoi_qualifier=args.aoi_qualifier,
            buffer_path=10,  # Default value
            buffer_feature=3,   # Default value
            takeoff_coords=args.takeoff_coords,
            takeoff_coords_projected=args.takeoff_coords_projected,
            output_folder=args.output_path,
            output_filename=args.output_filename,

            # BuildKMZ parameters
            approach=10,  # Default value
            buffer=6,     # Default value
            csv_path=args.csv,
            touch_sky=args.touch_sky,
            touch_sky_interval=args.touch_sky_interval,
            touch_sky_altitude=args.touch_sky_altitude,
            debug_mode=args.debug
        )
    
    # Validate config values
    if config.csv_path and config.features_path:
        raise ValueError("Cannot use both csv_path and features_path")
    
    # Validate touch-sky parameters
    if config.touch_sky:
        if config.touch_sky_interval < 5:
            raise ValueError("touch_sky_interval must be at least 5")
        if config.touch_sky_altitude > 200:
            raise ValueError("touch_sky_altitude cannot exceed 200 meters")
        if config.touch_sky_altitude < 16:
            raise ValueError("touch_sky_altitude cannot be less than 16 meters")

    # Validate BuildCSV parameters
    if config.features_path and not config.dsm_path:
        raise ValueError("DSM path must be provided when features path is specified")

    if (config.aoi_index or config.aoi_qualifier) and not config.aoi_path:
        raise ValueError("AOI path must be provided when aoi_index or aoi_qualifier is specified")

    if config.aoi_index and not config.aoi_qualifier:
        raise ValueError("aoi_index requires aoi_qualifier to be specified")

    if config.aoi_qualifier and not config.aoi_index:
        raise ValueError("aoi_qualifier requires aoi_index to be specified")
    
    if config.takeoff_coords_projected and not config.takeoff_coords:
        raise ValueError("takeoff_coords must be provided when takeoff_coords_projected is True")
    
    # Set default output path to input file directory if not specified
    if not config.output_folder:
        if config.csv_path:
            config.output_folder = str(Path(config.csv_path).parent)
        elif config.features_path:
            config.output_folder = str(Path(config.features_path).parent)

    # Set default output filename if not specified
    if not config.output_filename:
        if config.csv_path:
            input_filename = Path(config.csv_path).stem
        elif config.features_path:
            input_filename = Path(config.features_path).stem
        else:
            raise ValueError("Either 'csv_path' or 'features_path' must be provided")

        pattern = r'^[0-9a-z]{2,16}_(centroids|points|polygons)\d{0,2}$'
        if not re.match(pattern, input_filename):
            raise ValueError(
                f"""Input filename '{input_filename}' does not match the required pattern.
                Expected format: (drone_site)_(centroids|points|polygons)[version]
                Regex: {pattern}\n
                Specify an output filename using the 'output_filename' argument to bypass naming rule."""
            )
        drone_site = input_filename.split('_')[0]
        config.output_filename = f"{drone_site}_wpt"
        if config.aoi_qualifier and config.aoi_path is not None:
            config.output_filename += f"{config.aoi_qualifier}"
        # Extract version from filename if present (1 or 2 digits at the end)
        version_match = re.search(r'\d{1,2}$', input_filename)
        if version_match:
            config.output_filename += f"{version_match.group()}"

except ValidationError as e:
    print("Error: Invalid configuration")
    for error in e.errors():
        if error["type"] == "path_not_file":
            print("Input file not found.")
            print("Please ensure the file exists and the path is correct.")
        else:
            print(f"Validation error: {error['msg']}")
    sys.exit(1)

except Exception as e:
    print(f"Unexpected error: {str(e)}")
    sys.exit(1)
