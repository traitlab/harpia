<p align="center">
<img src="assets/harpia_logo.png" alt="harpia logo" height="400" width="400"><br/>
</p>

<h1 align="center">harpia</h1>

<p align="center">
<img src="https://img.shields.io/badge/python-3.11-blue" alt="Python 3.11">
<img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT">
<img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey" alt="Platform: Windows | Linux">
<a href="https://doi.org/10.1101/2025.09.02.673753"><img src="https://img.shields.io/badge/bioRxiv-red.svg" alt="Read the paper"></a>
<a href="https://doi.org/10.5281/zenodo.21982703"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.21982703.svg" alt="DOI"></a>
</p>

<p align="center">
harpia is an open-source Python library to program automatic close-up photo missions to carry out with the DJI Mavic 3E or Matrice 4E drones. It generates an optimized flight path from feature locations (selected tree crowns for example) to acquire the close-up photos, supporting tropical botanical and ecological work.
</p>

<p align="center">
  <a href="https://www.youtube.com/watch?v=80goMEifpc4" target="_blank">
    <img src="https://img.youtube.com/vi/80goMEifpc4/maxresdefault.jpg" alt="harpia demo" width="600"/>
  </a><br/>
  <a href="https://www.youtube.com/watch?v=80goMEifpc4" target="_blank"><font size="4"><em>▶️ See it in action</em></font></a>
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

### 🧭 Photo Heading
Chooses the aircraft yaw for each photo burst, trading frame consistency against flight time:
- **`north`** (default): rotate to true north before shooting, so photos of the same feature line up across missions
- **`arrival`**: keep the heading the drone arrived with, saving a rotation at every feature

### 🚁 Takeoff Site Coordinates
Optionally specify takeoff coordinates (`--takeoff-coords` or in YAML config). The first waypoint will be automatically selected as the closest one to the provided coordinates, optimizing the initial flight path from the takeoff location.
- **Purpose**: Start the mission from a defined first waypoint for improved route planning
- **Configurable**: Provide coordinates as `x y` (projected CRS) or `lat lon` (WGS84)

### 🌳 Crown Pre-Selection
Optionally shortlist candidate tree crowns before planning a mission, using `scripts/select_crowns.py`:
- **Input**: A candidate crowns layer, plus any combination of an AOI, a minimum area, an existing waypoints layer, a reference layer of known crowns, and a DSM
- **Process**: Applies up to five independent filters in sequence, reporting how many crowns each one removes
- **Output**: A filtered crowns layer ready to feed back in as the `--features` input

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
drone_model: m3e  # 'm3e', 'm4e' and 'm4d' are currently supported
output_folder: /path/to/output  # Optional
output_filename: my_mission  # Optional

# Flight settings
buffer: 6
approach: 10
photo_heading: north  # 'north' (default) or 'arrival'

# Waypoint generation settings
buffer_path: 10 # Optional
buffer_feature: 3 # Optional
takeoff_coords: [45.5572, -73.5558]  # Optional (lat lon for WGS84, or x y if projected)
takeoff_coords_projected: false  # Optional

# Area of Interest (AOI) settings
aoi_path: /path/to/aoi.gpkg # Optional
aoi_index: 1 # Optional - selects the AOI polygon by 1-based position
aoi_qualifier: north # Optional - suffix for output filenames; used alone, selects the AOI by its 'qualifier' column

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
- `--csv`: Path to existing waypoints CSV file
- `--features, -f`: Path to input features file (GeoPackage, Shapefile)
- `--dsm, -d`: Path to DSM raster file
- `--drone-model, -m`: Model of the drone to carry out the mission ('m3e', 'm4e' or 'm4d')
- `--output-path, -o`: Output directory path (optional)
- `--output-filename, -n`: Custom output filename without extension (optional)

#### 🗺️ Area of Interest (AOI) Settings
- `--aoi, -a`: Path to AOI file for filtering features (optional)
- `--aoi-index, -i`: 1-based index of the AOI polygon to use; requires `--aoi-qualifier` (optional)
- `--aoi-qualifier, -q`: Qualifier appended to output filenames, up to 8 characters (optional)

There are two ways to select a single polygon from the AOI file:
- **By position**: pass both `--aoi-index` and `--aoi-qualifier`.
- **By attribute**: pass `--aoi-qualifier` on its own. The AOI file must then contain a `qualifier` column, and the feature whose value matches is selected.

#### 🎯 Waypoint Generation Settings
- `--takeoff-coords, -t`: Takeoff site coordinates as two floats: x y OR lat lon (optional)
- `--takeoff-coords-projected`: Flag to indicate takeoff coordinates are in projected CRS (default: False (WGS84)) (optional)

#### 📷 Photo Settings
- `--photo-heading`: Aircraft yaw for each photo burst — `north` (default) rotates to true north, `arrival` keeps the heading flown in with (optional)

#### 🌤️ Touch-Sky Settings
- `--touch-sky, -s`: Enable touch-sky feature (default: False)
- `--touch-sky-interval`: Number of features between touch-sky actions (default: 10, min: 5)
- `--touch-sky-altitude`: Touch-sky altitude in meters above DSM (default: 100, min: 16, max: 200)

#### 🔧 System Settings
- `--debug, -v`: Run in debug mode

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
Select the AOI polygon by position:
```bash
python main.py \
  --features data/site_polygons1.gpkg \
  --dsm data/dsm.tif \
  --aoi data/aoi.gpkg \
  --aoi-index 2 \
  --aoi-qualifier north
```

Or select it by its `qualifier` attribute, without knowing its position:
```bash
python main.py \
  --features data/site_polygons1.gpkg \
  --dsm data/dsm.tif \
  --aoi data/aoi.gpkg \
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
- **Attributes**: A `qualifier` column is required only when selecting the AOI with `--aoi-qualifier` alone

## 📊 Output Files

The pipeline generates several output files:

### Waypoints Files
- `{site}_wpt[qualifier][version]_{drone_model}.csv`: Waypoints for mission generation
- `{site}_wpt[qualifier][version]_{drone_model}.gpkg`: Spatial waypoints data to visualize in GIS software

When an existing waypoints CSV is passed with `--csv`, a trailing drone-model suffix is stripped from its name and the current model appended, so the same CSV can be re-run for another drone without stacking suffixes.

### CSV Format
The output CSV from features-based waypoint generation contains the following columns:
- `point_id`: Unique identifier for each point
- `cluster_id`: Cluster identifier if available (default: 0)
- `type`: Point type ('wpt' for waypoints, 'cpt' for checkpoints)
- `lon_x`: Longitude in WGS84
- `lat_y`: Latitude in WGS84
- `elevation_from_dsm`: Ellipsoidal elevation from DSM in meters
- `order`: Waypoint order for mission planning

CSV as input needs to respect the format above. It is validated on load: the columns listed above must be present, `lon_x`, `lat_y` and `elevation_from_dsm` must be numeric, and the file must contain at least one `wpt` row and one `cpt` row.

### Mission Files
- `template.kml`: KML template for DJI mission
- `waylines.wpml`: WPML waylines for DJI drone
- `mission.kmz`: Complete mission package to upload to DJI Pilot 2 app

## 🌳 Crown Pre-Selection (Optional)

`scripts/select_crowns.py` narrows a layer of candidate tree crowns down to a shortlist worth visiting. It applies up to five filters, each of which runs **only when its input is supplied**:

| # | Filter | Enabled by | Keeps |
|---|--------|------------|-------|
| 1 | Area of interest | `--aoi` | Crowns inside the AOI polygon |
| 2 | Minimum area | `--min-area` | Crowns at or above a minimum area in m² |
| 3 | Already visited | `--waypoints` | Crowns that do not already contain a waypoint |
| 4 | Already known | `--exclude` | Crowns not overlapping a reference layer |
| 5 | DSM relief | `--dsm` | Crowns not overtopped by their immediate surroundings |

Filters run in the order above, each operating on the survivors of the previous one, and every step reports how many crowns it removed.

```bash
python scripts/select_crowns.py \
  --crowns crowns.gpkg \
  --output selected_crowns.gpkg \
  --aoi drone_sites.gpkg --site-id bcipearson \
  --min-area 25 \
  --waypoints 2024_bci_wpt.gpkg \
  --exclude predictions_above80.gpkg \
  --dsm dsm.tif --buffer-large 8 --buffer-small 1 --max-dsm-diff 5
```

Every setting can also come from a YAML file, with command-line arguments taking precedence:

```bash
python scripts/select_crowns.py --config config/select_crowns.yaml
```

See [`config/select_crowns_template.yaml`](config/select_crowns_template.yaml) for the full list of settings and their defaults.

The resulting layer can be used directly as the `--features` input to `main.py`. Name it to match the features naming convention (for example `bcipearson_polygons.gpkg`), or pass `--output-filename` to `main.py` to bypass that rule.

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
