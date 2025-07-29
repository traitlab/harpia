<p align="center">
<img src="assets/harpia_logo.png" alt="harpia logo" height="400" width="400"><br/>
</p>

<h1 align="center">harpia</h1>

<p align="center">
<img src="https://img.shields.io/badge/python-3.11-blue" alt="Python 3.11">
<img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT">
<img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey" alt="Platform: Windows | Linux">
</p>

<p align="center">
harpia is an open-source Python library to program automatic close-up photo missions for use with the DJI Mavic 3E drone
</p>

## ✨ Key Features

### 🎯 Waypoint Generation
Automatically generates optimized flight paths from tree/feature locations:
- **Input**: Features (centroids, points or polygons) from GeoPackage/Shapefile + Digital Surface Model (DSM)
- **Process**: Extracts elevations, solves Traveling Salesman Problem (TSP) for optimal route, creates path checkpoints above obstacles
- **Output**: Waypoints CSV with precise coordinates and flight heights above features

### 📦 KMZ Mission Package Creation
Converts waypoints into DJI-compatible mission files:
- **Template KML**: Defines mission structure and flight parameters
- **Waylines WPML**: Contains detailed waypoint sequences and actions
- **KMZ Package**: Complete mission file ready for DJI Pilot 2 app

### 🌤️ Touch-Sky Feature
Periodically ascends to a higher altitude to re-establish signal and transmit updated RTK corrections to the drone:
- **Purpose**: Fly to higher altitude periodically to restore connection between controller and drone before losing RTK signal
- **Configurable**: Set interval (every N waypoints) and altitude (up to 200m above DSM)

### 🚁 Takeoff Site Coordinates
Optionally specify takeoff site coordinates (`--takeoff-site-coords` or in YAML config). The first waypoint will be automatically selected as the closest one to the provided coordinates, optimizing the initial flight path from the takeoff location.
- **Purpose**: Start the mission from a defined first waypoint for improved route planning
- **Configurable**: Provide coordinates as `[x, y]` (projected CRS) or `lon lat` (WGS84)

## 🔧 Setup

Clone the repository to your local machine:

```bash
git clone https://github.com/traitlab/harpia.git
cd harpia
```

Install the required Python packages in a python 3.11 conda environment:

```bash
conda create -n harpia python=3.11
conda activate harpia
pip install -r requirements.txt
```

## ⚙️ Configuration

It is possible to pass a YAML configuration file or to use command-line arguments when running the pipeline.

### Using YAML Configuration

Create a configuration file (e.g., `config.yaml`) with your settings. A detailed configuration template, including explicit descriptions for each argument, is available in the `config` folder.

```yaml
# General settings
approach: 10
buffer: 6

# Either `csv_path` or `features_path` must be provided.
# Input waypoints
csv_path: /path/to/waypoints.csv # Optional

# Feature-based waypoint generation settings
features_path: /path/to/features.gpkg # Optional
dsm_path: /path/to/dsm.tif # Optional

aoi_path: /path/to/aoi.gpkg # Optional
aoi_index: 1 # Optional
aoi_qualifier: north # Optional

buffer_path: 10 # Optional
takeoff_coords: [-73.5558, 45.5572]  # Optional
takeoff_coords_projected: false  # Optional

# Touch-sky settings
touch_sky: false
touch_sky_interval: 10
touch_sky_altitude: 100

# Output settings
output_folder: /path/to/output  # Optional
output_filename: custom_mission  # Optional

# Debug mode
debug_mode: false
```

### Available Command Line Arguments

#### Core Arguments
- `--config, -c`: Path to YAML configuration file
- `--csv, -csv`: Path to existing waypoints CSV file
- `--output-path, -op`: Output directory path
- `--output-filename, -of`: Custom output filename without extension

#### Flight Parameters
- `--approach, -a`: Approach height above tree crown in meters (default: 10)
- `--buffer, -b`: Buffer height above tree crown in meters (default: 6)

#### BuildCSV Parameters (for generating waypoints from features)
- `--features, -f`: Path to input features file (GeoPackage, Shapefile)
- `--dsm, -dsm`: Path to DSM raster file
- `--aoi, -aoi`: Path to AOI file for filtering features (optional)
- `--aoi-index, -i`: Index of AOI polygon to use, 1-based (default: 1)
- `--aoi-qualifier, -q`: Qualifier for AOI in output filenames (optional)
- `--buffer-path`: Buffer for path checkpoints in meters (default: 10)
- `--buffer-tree`: Buffer for tree features in meters (default: 3)
- `--takeoff-site-coords, -to`: Takeoff site coordinates as two floats: x y
- `--takeoff-coords-projected, -proj`: Flag to indicate takeoff coordinates are in projected CRS (same as DSM). Default: False (WGS84)

#### Touch-Sky Parameters
- `--touch-sky, -ts`: Enable touch-sky feature (default: false)
- `--touch-sky-interval, -n`: Number of waypoints between touch-sky actions (default: 10, min: 5)
- `--touch-sky-altitude, -alt`: Touch-sky altitude in meters above DSM (default: 100, max: 200)

#### Other Options
- `--debug, -d`: Run in debug mode

## 🚀 Usage Examples

Run with configuration file:
```bash
python main.py --config config.yaml
```

### Using Command Line Arguments

#### Option 1: Generate waypoints from features
```bash
python main.py \
  --features data/trees.gpkg \
  --dsm data/dsm.tif \
  --aoi data/aoi.gpkg \
  --aoi-index 1 \
  --aoi-qualifier north \
```

#### Option 2: Use existing CSV file (legacy workflow)
```bash
python main.py \
  --csv waypoints.csv \
  --output-folder /path/to/output \
  --output-filename my_mission \
  --touch-sky \
```

### Example 1: Complete workflow from features
```bash
python main.py \
  --features-path data/trees_centroids.gpkg \
  --dsm-path data/site_dsm.tif \
  --output results/ \
  --approach 12 \
  --buffer 8 \
  --touch-sky \
  --touch-sky-interval 15
```

### Example 2: Using existing waypoints
```bash
python main.py \
  --csv data/waypoints.csv \
  --output results/ \
  --approach 10 \
  --buffer 6
```

### Example 3: With AOI filtering
```bash
python main.py \
  --features-path data/all_trees.gpkg \
  --dsm-path data/dsm.tif \
  --aoi-path data/study_area.gpkg \
  --aoi-index 2 \
  --aoi-qualifier "_area2" \
  --output results/
```

## 📋 Input Data Requirements

### Features File
- **Format**: GeoPackage (.gpkg) or Shapefile (.shp)
- **Geometry**: Point, Polygon, or MultiPolygon
- **Naming convention**: `{site}_{centroids|polygons}[version].{ext}`
  - Examples: `site1_centroids.gpkg`, `area2_polygons3.shp`
- **CRS**: Any projected coordinate system

### DSM (Digital Surface Model)
- **Format**: GeoTIFF (.tif, .tiff)
- **Content**: Elevation values in meters
- **CRS**: Should match or be compatible with features

### AOI (Area of Interest) - Optional
- **Format**: GeoPackage (.gpkg) or Shapefile (.shp)  
- **Geometry**: Polygon or MultiPolygon
- **Purpose**: Filter features to specific areas

## 📊 Output Files

The pipeline generates several output files:

### Waypoints Files
- `{site}_wpt[qualifier][version].csv`: Waypoints for mission planning
- `{site}_wpt[qualifier][version].gpkg`: Spatial waypoints data

### Mission Files
- `template.kml`: KML template for DJI mission
- `waylines.wpml`: WPML waylines for DJI drone
- `mission.kmz`: Complete mission package

### CSV Format
The output CSV contains the following columns:
- `point_id`: Unique identifier for each point
- `cluster_id`: Cluster identifier if available (default: 0)
- `type`: Point type ('wpt' for waypoints, 'cpt' for checkpoints)
- `lon_x`: Longitude in WGS84
- `lat_y`: Latitude in WGS84
- `elevation_from_dsm`: Elevation from DSM in meters
- `order`: Waypoint order for mission planning
