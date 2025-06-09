import argparse
import os
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from model.config import Config


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
    description='Generate the KMZ from a list of coordinates (lat, lon, elevation) in a CSV file.')
parser.add_argument('--config', '-s', type=str, required=False,
                    help='Path to the configuration file. Other choice is to provide the --csv option.')
parser.add_argument('--csv', '-c', type=str, required=False,
                    help='Path to the input CSV file containing waypoints. Other choice is to provide the --config option.')
parser.add_argument('--output', '-o', type=str, required=None,
                    help='Output directory path (default: same directory as input file)')
parser.add_argument('--approach', '-a', type=float, default=10,
                    help='Approach above the tree crown in meters (default: 10)')
parser.add_argument('--buffer', '-b', type=float, default=6,
                    help='Buffer above the tree crown in meters (default: 6)')
parser.add_argument('--touch-sky', '-t', type=bool, default=True,
                    help='Enable touch-sky feature where drone flies up periodically (default: True)')
parser.add_argument('--touch-sky-interval', '-n', type=int, default=10,
                    help='Number of placemarks between each touch-sky action (default: 10, min: 5)')
parser.add_argument('--touch-sky-altitude', '-alt', type=float, default=100,
                    help='Altitude in meters above DSM for touch-sky action (default: 100, max: 200)')
parser.add_argument('--debug', '-d', action='store_true',
                    help='Run in debug mode (default: False)')

args = parser.parse_args()

# Validate that either --config or --csv is provided
if not args.config and not args.csv:
    parser.error("Either --config or --csv must be provided")
    sys.exit(1)

# Validate touch-sky parameters
if args.touch_sky:
    if args.touch_sky_interval < 5:
        parser.error("--touch-sky-interval must be at least 5")
    if args.touch_sky_altitude > 200:
        parser.error("--touch-sky-altitude cannot exceed 200 meters")

# Set default output path to input file directory if not specified
if args.output is None:
    input_path = args.config if args.config else args.csv
    args.output = str(Path(input_path).parent)

try:
    # Create config object
    if args.config:
        config = load_config(args.config)
        config.debug_mode = args.debug
    else:
        # Get base_name from CSV file path and replace special characters with '-'
        base_name = Path(args.csv).stem  # Get filename without extension
        for char in ['/', '\\', '|', '?', '*', '.', '_']:
            base_name = base_name.replace(char, '-')
        
        # Create a default Config object with command line values
        config = Config(
            approach=args.approach,
            buffer=args.buffer,
            base_path=args.output,
            base_name=base_name,
            points_csv_file_path=args.csv,
            touch_sky=args.touch_sky,
            touch_sky_interval=args.touch_sky_interval,
            touch_sky_altitude=args.touch_sky_altitude,
            debug_mode=args.debug
        )
except ValidationError as e:
    print("Error: Invalid configuration")
    for error in e.errors():
        if error["type"] == "path_not_file":
            print(f"CSV file not found: {args.csv}")
            print("Please ensure the CSV file exists and the path is correct.")
        else:
            print(f"Validation error: {error['msg']}")
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error: {str(e)}")
    sys.exit(1)
