import argparse
import os
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
parser.add_argument('--config', '-c', type=str, required=False,
                    help='Path to the configuration file. Other choice is to provide the --csv or --features arguments.')
parser.add_argument('--csv', '-csv', type=str, required=False,
                    help='Path to the input CSV file in the right format containing waypoints. If not provided, it will be generated from features.')
parser.add_argument('--touch-sky', '-ts', action='store_true', default=False,
                    help='Enable touch-sky feature where drone flies up periodically (default: False)')
parser.add_argument('--touch-sky-interval', '-n', type=int, default=10,
                    help='Number of placemarks between each touch-sky action (default: 10, min: 5)')
parser.add_argument('--touch-sky-altitude', '-alt', type=int, default=100,
                    help='Altitude in meters above DSM for touch-sky action (default: 100, max: 200)')

# Arguments for BuildCSV
parser.add_argument('--features', '-f', type=str, required=False,
                    help='Path to the input features file (e.g., GeoPackage, Shapefile).')
parser.add_argument('--dsm', '-dsm', type=str, required=False,
                    help='Path to the DSM raster file.')
parser.add_argument('--aoi', '-aoi', type=str, required=False,
                    help='Path to the AOI file to filter features.')
parser.add_argument('--aoi-index', '-i', type=int,
                    help='Index of the AOI polygon to use.')
parser.add_argument('--aoi-qualifier', '-q', type=str,
                    help='Qualifier for the AOI to be used in output filenames.')
parser.add_argument('--takeoff-site-coords', '-to', type=float, nargs=2,
                     metavar=('X', 'Y'), required=False,
                     help='Coordinates (x, y) of the takeoff site.')
parser.add_argument('--output-path', '-op', type=str, required=False,
                    help='Custom output directory path (default: same directory as input file)')
parser.add_argument('--output-filename', '-of', type=str, required=False,
                    help='Custom output filename without extension (default: same as input file). ')

parser.add_argument('--debug', '-d', action='store_true',
                    help='Run in debug mode (default: False)')

args = parser.parse_args()

# Validate that either --config or --csv or --features is provided
if not args.config and not args.csv and not args.features:
    parser.error("Either --config, --csv or --features must be provided")
    sys.exit(1)

# Validate that only one of --config, --csv or --features is provided
if args.config and (args.csv or args.features):
    parser.error("Cannot use --config with --csv or --features")
    sys.exit(1)

if args.csv and args.features:
    parser.error("Cannot use both --csv and --features")
    sys.exit(1)

# Validate touch-sky parameters
if args.touch_sky:
    if args.touch_sky_interval < 5:
        parser.error("--touch-sky-interval must be at least 5")
    if args.touch_sky_altitude > 200:
        parser.error("--touch-sky-altitude cannot exceed 200 meters")

# Validate BuildCSV parameters
if args.features and not args.dsm:
    parser.error("--dsm must be provided when --features is specified")

if (args.aoi_index or args.aoi_qualifier) and not args.aoi:
    parser.error("--aoi must be provided when --aoi-index or --aoi-qualifier is specified")

# Set default output path to input file directory if not specified
if args.output_path is None:
    if args.config:
        args.output_path = str(Path(args.config).parent)
    elif args.csv:
        args.output_path = str(Path(args.csv).parent)
    elif args.features:
        args.output_path = str(Path(args.features).parent)
    else:
        # Fallback to current working directory
        args.output_path = "."

try:
    # Create config object
    if args.config:
        config = load_config(args.config)
        config.debug_mode = args.debug
    else:
        # Get base_name from input file and replace special characters with '-'. Prioritize user-provided output_filename if available
        if args.output_filename:
            base_name = args.output_filename
        elif args.csv:
            base_name = Path(args.csv).stem
        elif args.features:
            base_name = Path(args.features).stem
        else:
            base_name = "output"  # Fallback name
        for char in ['/', '\\', '|', '?', '*', '.', '_']:
            base_name = base_name.replace(char, '-')
        
        # Create a default Config object with command line values
        config = Config(
            # BuildCSV parameters
            features_path=args.features,
            dsm_path=args.dsm,
            aoi_path=args.aoi,
            aoi_index=args.aoi_index,
            aoi_qualifier=args.aoi_qualifier,
            buffer_path=10,  # Default value
            buffer_tree=3,   # Default value
            takeoff_site_coords=args.takeoff_site_coords,
            output_folder=args.output_path,
            output_filename=args.output_filename,

            # BuildKMZ parameters
            approach=10,  # Default value
            buffer=6,     # Default value
            base_name=base_name,
            csv_path=args.csv,
            touch_sky=args.touch_sky,
            touch_sky_interval=args.touch_sky_interval,
            touch_sky_altitude=args.touch_sky_altitude,
            debug_mode=args.debug
        )

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
