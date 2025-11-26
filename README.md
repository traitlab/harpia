<p align="center">
<img src="assets/harpia_logo.png" alt="harpia logo" height="400" width="400"><br/>
</p>

<h1 align="center">harpia</h1>

<p align="center">
<img src="https://img.shields.io/badge/python-3.11-blue" alt="Python 3.11">
<img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT">
<img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey" alt="Platform: Windows | Linux">
<a href="https://doi.org/10.1101/2025.09.02.673753">
  <img src="https://img.shields.io/badge/bioRxiv-red.svg" alt="Read the paper">
</a>
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
Optionally specify takeoff coordinates (`--takeoff-coords` or in YAML config). The first waypoint will be automatically selected as the closest one to the provided coordinates, optimizing the initial flight path from the takeoff location.
- **Purpose**: Start the mission from a defined first waypoint for improved route planning
- **Configurable**: Provide coordinates as `x y` (projected CRS) or `lat lon` (WGS84)

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
# Input/Output settings
csv_path: /path/to/waypoints.csv # Optional
features_path: /path/to/features.gpkg # Optional
dsm_path: /path/to/dsm.tif # Optional
output_folder: /path/to/output  # Optional
output_filename: my_mission  # Optional

# Flight settings
buffer: 6
approach: 10

# Waypoint generation settings
buffer_path: 10 # Optional
buffer_feature: 3 # Optional
takeoff_coords: [45.5572, -73.5558]  # Optional (lat lon for WGS84, or x y if projected)
takeoff_coords_projected: false  # Optional

# Area of Interest (AOI) settings
aoi_path: /path/to/aoi.gpkg # Optional
aoi_index: 1 # Optional
aoi_qualifier: north # Optional

# Touch-sky settings
touch_sky: false
touch_sky_interval: 10
touch_sky_altitude: 100

# System settings
debug_mode: false
```

### Available Command Line Arguments

#### 📁 Input/Output Settings
- `--config, -c`: Path to YAML configuration file
- `--csv, -csv`: Path to existing waypoints CSV file
- `--features, -f`: Path to input features file (GeoPackage, Shapefile)
- `--dsm, -dsm`: Path to DSM raster file
- `--output-path, -op`: Output directory path (optional)
- `--output-filename, -of`: Custom output filename without extension (optional)

#### 🗺️ Area of Interest (AOI) Settings
- `--aoi, -aoi`: Path to AOI file for filtering features (optional)
- `--aoi-index, -i`: Index of AOI polygon to use (optional)
- `--aoi-qualifier, -q`: Qualifier for AOI in output filename (optional)

#### 🎯 Waypoint Generation Settings
- `--takeoff-coords, -to`: Takeoff site coordinates as two floats: x y OR lat lon (optional)
- `--takeoff-coords-projected, -proj`: Flag to indicate takeoff coordinates are in projected CRS (default: False (WGS84)) (optional)

#### 🌤️ Touch-Sky Settings
- `--touch-sky, -ts`: Enable touch-sky feature (default: False)
- `--touch-sky-interval, -n`: Number of features between touch-sky actions (default: 10, min: 5)
- `--touch-sky-altitude, -alt`: Touch-sky altitude in meters above DSM (default: 100, min: 16, max: 200)

#### 🔧 System Settings
- `--debug, -d`: Run in debug mode

## 🚀 Usage Examples

### Run with Configuration File

```bash
python main.py --config config.yaml
```
### Run with Command Line Arguments
(replace `\` with `^` for Windows Command Prompt)

#### Option 1: Use existing CSV file (legacy workflow)
with custom output settings and `--touch-sky` option to enable periodic ascents

```bash
python main.py \
  --csv waypoints.csv \
  --output-path /path/to/output \
  --output-filename my_mission \
  --touch-sky
```

#### Option 2: Generate waypoints from features
```bash
python main.py \
  --features data/site_centroids.gpkg \
  --dsm data/dsm.tif
```

#### Option 3: Generate waypoints from features with AOI filtering
```bash
python main.py \
  --features data/site_polygons1.gpkg \
  --dsm data/dsm.tif \
  --aoi data/aoi.gpkg \
  --aoi-index 2 \
  --aoi-qualifier north
```

## 📋 Input Data Requirements

### Features File
- **Format**: GeoPackage (.gpkg) or Shapefile (.shp)
- **Geometry**: Point, Polygon, or MultiPolygon
- **Naming convention**: `{site}_{centroids|points|polygons}[version].{ext}`
  - Examples: `site_centroids.gpkg`, `area_polygons3.shp`
- **CRS**: Any projected coordinate system that matches the DSM and AOI
- **Unique Identifier**: Each feature should have a unique `point_id` or `FID` that will be used for naming output pictures

### DSM (Digital Surface Model)
- **Format**: GeoTIFF (.tif, .tiff)
- **Content**: Ellipsoidal elevation values in meters
- **CRS**: Any projected coordinate system that matches the features and AOI

### AOI (Area of Interest) - Optional
- **Format**: GeoPackage (.gpkg) or Shapefile (.shp)  
- **Geometry**: Polygon or MultiPolygon
- **Purpose**: Filter features to specific areas
- **CRS**: Any projected coordinate system that matches the features and DSM

## 📊 Output Files

The pipeline generates several output files:

### Waypoints Files
- `{site}_wpt[qualifier][version].csv`: Waypoints for mission generation
- `{site}_wpt[qualifier][version].gpkg`: Spatial waypoints data to visualize in GIS software

### CSV Format
The output CSV from features-based waypoint generation contains the following columns:
- `point_id`: Unique identifier for each point
- `cluster_id`: Cluster identifier if available (default: 0)
- `type`: Point type ('wpt' for waypoints, 'cpt' for checkpoints)
- `lon_x`: Longitude in WGS84
- `lat_y`: Latitude in WGS84
- `elevation_from_dsm`: Ellipsoidal elevation from DSM in meters
- `order`: Waypoint order for mission planning

CSV as input needs to respect the format above.

### Mission Files
- `template.kml`: KML template for DJI mission
- `waylines.wpml`: WPML waylines for DJI drone
- `mission.kmz`: Complete mission package to upload to DJI Pilot 2 app

## 📚 Citation
If you use harpia in your research, please cite our paper (bioRxiv preprint):

```bibtex
@misc{Lalibert2025harpia,
    title={Seeing the forest and the trees: a workflow for automatic acquisition of ultra-high resolution drone photos of tropical forest canopies to support botanical and ecological studies},
    author={Laliberté, Etienne and Caron-Guay, Antoine and Le Falher, Vincent and Tougas, Guillaume and Muller-Landau, Helene C. and Rivas-Torres, Gonzalo and Walla, Thomas R. and Baudchon, Hugo and Hernandez, Mélvin and Buenaño, Adrian and Weber, Anna and Chambers, Jeffrey and Inuma, Jomber and Araúz, Fernando and Valdes, Jorge and Hernández, Andrés and Brassfield, David and Sérgio, Paulo and Vasquez, Vicente and Simonetti, Adriana and Marra, Daniel M. and Vasconcelos, Caroline and Vaca, Jarol F. and Rivadeneyra, Geovanny and Illanes, José and Salagaje-Muela, Luis A. and Gualinga, Jefferson},
    year={2025},
    url={https://www.biorxiv.org/content/10.1101/2025.09.02.673753v1},
    doi={10.1101/2025.09.02.673753},
    keywords={Unoccupied aerial vehicle (UAV),biodiversity,monitoring,RGB imagery,canopy,remote tree-survey,Panama,Ecuador,Brazil,tropical tree diversity}
}
```