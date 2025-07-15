import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import re

from ortools.constraint_solver import routing_enums_pb2, pywrapcp
from pathlib import Path
from rasterstats import zonal_stats
from shapely.geometry import LineString

class BuildCSV:
    # -------------------------------------------------------------------------
    def __init__(self, features_path, dsm_path, aoi_path=None, aoi_index=1, aoi_qualifier="", buffer_path=10, buffer_tree=3, takeoff_site_coords=None):
        self.features_path = features_path
        self.dsm_path = dsm_path
        self.aoi_path = aoi_path
        self.aoi_index = aoi_index
        self.aoi_qualifier = aoi_qualifier
        self.buffer_path = buffer_path
        self.buffer_tree = buffer_tree
        self.takeoff_site_coords = takeoff_site_coords
    
    # -------------------------------------------------------------------------
    def run(self, output_folder=None, output_filename=None):
        """
        Full workflow: process features, DSM, TSP, checkpoints, and export results.
        """
        # 1. Read features (with AOI filtering if provided)
        features = self.read_features()
        # 2. Read DSM raster
        dsm = self.read_dsm()
        # 3. Align CRS (if needed)
        features = self.align_features_to_dsm(features, dsm)
        # 4. Extract tree elevations
        features = self.extract_features_elevations(features)
        # 5. Build distance matrix and get coordinates
        coords = np.array([[geom.x, geom.y] for geom in features.geometry])
        distance_matrix = self.build_distance_matrix(features.geometry.tolist())
        # 6. Solve TSP (optionally with takeoff site)
        tsp_route = self.solve_tsp_ortools(distance_matrix, takeoff_site_coords=self.takeoff_site_coords, waypoints_coords=coords)
        # 7. Reorder features according to TSP
        waypoints = self.get_tsp_solution_df(features, tsp_route)
        # 8. Extract path checkpoints
        checkpoints = self.extract_path_checkpoints(waypoints)
        # 9. Interleave waypoints and checkpoints
        merged = self.merge_waypoints_and_checkpoints(waypoints, checkpoints)
        # 10. Transform to WGS84 for export
        merged_gdf = gpd.GeoDataFrame(merged, geometry='geometry', crs=features.crs)
        merged_gdf = self.to_wgs84(merged_gdf)
        # 11. Format for CSV: extract lon/lat, rename columns, drop geometry
        merged_gdf['lon_x'] = merged_gdf.geometry.x
        merged_gdf['lat_y'] = merged_gdf.geometry.y
        # Add placeholder columns if missing
        if 'cluster_id' not in merged_gdf:
            merged_gdf['cluster_id'] = 0
        merged_gdf['elevation_from_dsm'] = merged_gdf['elev']
        gpkg_gdf = merged_gdf.drop(columns=['elevation_from_dsm'])
        gpkg_gdf = gpkg_gdf[gpkg_gdf['type'] != 'cpt']
        csv_df = merged_gdf[['point_id', 'cluster_id', 'type', 'lon_x', 'lat_y', 'elevation_from_dsm', 'order']]
        # 12. Export
        if output_filename is None:
            input_filename = Path(self.features_path).stem
            pattern = r'^[0-9a-z]{2,16}_(centroids|points|polygons)\d?$'
            if not re.match(pattern, input_filename):
                raise ValueError(
                    f"""Input filename '{input_filename}' does not match the required pattern.
                        Expected format: (drone_site)_(centroids|points|polygons)[version] - Regex: {pattern}
                        Specify an output filename using the 'output_filename' argument to bypass naming rule.""")
            drone_site = input_filename.split('_')[0]
            output_filename = f"{drone_site}_wpt"
            if self.aoi_qualifier and self.aoi_path is not None:
                output_filename += f"{self.aoi_qualifier}"
            # Extract version from filename if present (digit at the end)
            version_match = re.search(r'\d$', input_filename)
            if version_match:
                output_filename += f"{version_match.group()}"
        if output_folder is None:
            output_folder = Path(self.features_path).parent
            print(f"Output folder not specified, using features path directory: {output_folder}")
        else:
            output_folder = Path(output_folder)
        output_gpkg_path = output_folder / f"{output_filename}.gpkg"
        output_csv_path = output_folder / f"{output_filename}.csv"
        self.export_to_gpkg(gpkg_gdf, output_gpkg_path)
        self.export_to_csv(csv_df, output_csv_path)
        
        return gpkg_gdf, csv_df, output_csv_path
    
    # -------------------------------------------------------------------------
    def read_features(self):
        features = gpd.read_file(self.features_path, engine='pyogrio', fid_as_index=True)
        
        # Check geometry type
        geom_type = features.geometry.geom_type.unique()
        if all(gt in ['Polygon', 'MultiPolygon'] for gt in geom_type):
            # Convert polygons to centroids
            # features['geometry'] = features.centroid
            # or use representative_point() if you want a point inside the polygon
            features['geometry'] = features.geometry.representative_point()
        elif all(gt == 'Point' for gt in geom_type):
            pass
        else:
            raise ValueError(f"Unsupported geometry type(s): {geom_type}. Input features file should contain only Polygon, MultiPolygon or Point geometries.")
        
        # Add 'point_id' column if missing
        if 'point_id' not in features.columns:
            features['point_id'] = features['FID'] if 'FID' in features.columns else features.index

        # If AOI is provided, filter features
        if self.aoi_path is not None:
            aoi = gpd.read_file(self.aoi_path)
            # Optionally select a specific AOI by index
            if self.aoi_index is not None:
                aoi = aoi.iloc[[self.aoi_index - 1]]  # 1-based index
            # Ensure CRS matches
            if features.crs != aoi.crs:
                print(f"Warning: AOI CRS ({aoi.crs}) does not match features CRS ({features.crs}). Reprojecting AOI to features CRS.")
                aoi = aoi.to_crs(features.crs)

            mask = features.geometry.intersects(aoi.unary_union)
            features = features[mask]
        
        return features
    
    # -------------------------------------------------------------------------
    def read_dsm(self):
        """Read the DSM raster file using rasterio and return the raster object."""
        dsm = rasterio.open(self.dsm_path)
        return dsm
    
    # -------------------------------------------------------------------------
    def align_features_to_dsm(self, features, dsm):
        """Ensure features are in the same CRS as the DSM raster. Returns reprojected features if needed."""
        dsm_crs = dsm.crs
        if features.crs != dsm_crs:
            print(f"Warning: Features CRS ({features.crs}) does not match DSM CRS ({dsm_crs}). Reprojecting features to DSM CRS.")
            features = features.to_crs(dsm_crs)
        return features
    
    # -------------------------------------------------------------------------
    def extract_features_elevations(self, features):
        """
        For each feature, create a buffer and extract the DSM elevation value. Returns a GeoDataFrame with an 'elev' column.
        """
        # Create buffer around centroids
        buffers = features.buffer(self.buffer_tree)
        gdf_buffers = gpd.GeoDataFrame(geometry=buffers, crs=features.crs)

        stats = zonal_stats(gdf_buffers, self.dsm_path, stats=["max"])
        max_elev = [s["max"] for s in stats]
        features = features.copy()
        features["elev"] = max_elev
        return features
    
    # -------------------------------------------------------------------------
    def build_distance_matrix(self, features):
        """
        Build a distance matrix for the features. Returns a 2D numpy array of distances.
        """
        num_features = len(features)
        distance_matrix = np.zeros((num_features, num_features))

        for i in range(num_features):
            for j in range(num_features):
                if i != j:
                    distance_matrix[i][j] = features[i].distance(features[j])
        
        return distance_matrix
    
    # -------------------------------------------------------------------------
    @staticmethod
    def solve_tsp_ortools(distance_matrix, takeoff_site_coords=None, waypoints_coords=None):
        """
        Solve TSP using Google OR-Tools. Scales distances by 1000 to use integers.
        If takeoff_site_coords and waypoints_coords are provided, use takeoff site as the start and find the nearest waypoint.
        """
        # Scale the distance matrix by 1000 and convert to int
        scaled_matrix = (distance_matrix * 1000).astype(int)
        
        start_index = 0
        if takeoff_site_coords is not None and waypoints_coords is not None:
            # Compute distances from takeoff site to all waypoints
            takeoff = np.array(takeoff_site_coords)
            dists = np.linalg.norm(waypoints_coords - takeoff, axis=1)
            start_index = np.argmin(dists)
        manager = pywrapcp.RoutingIndexManager(len(scaled_matrix), 1, start_index)
        routing = pywrapcp.RoutingModel(manager)
        
        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(scaled_matrix[from_node][to_node])
        
        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
        
        # Set search parameters
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        search_parameters.time_limit.seconds = 30
        # or no wait
        # search_parameters.log_search = True
        # search_parameters.first_solution_strategy = (
        #     routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
        
        # Solve the problem
        solution = routing.SolveWithParameters(search_parameters)
        if solution:
            # Extract the route
            route = []
            index = routing.Start(0)
            while not routing.IsEnd(index):
                route.append(manager.IndexToNode(index))
                index = solution.Value(routing.NextVar(index))
            return route
        return None
    
    # -------------------------------------------------------------------------
    def get_tsp_solution_df(self, features, route):
        """
        Given a list of feature indices (route), return a DataFrame with the features in TSP order and an 'order' column.
        """
        # Reorder features according to the TSP route
        ordered_features = features.iloc[route].copy()
        ordered_features['order'] = range(1, len(route) + 1)
        ordered_features['type'] = 'wpt'
        cols = ['point_id', 'type', 'geometry', 'elev', 'order']
        ordered_features = ordered_features[cols]
        return ordered_features
    
    # -------------------------------------------------------------------------
    def extract_path_checkpoints(self, ordered_features):
        """
        For each consecutive pair of waypoints, create a buffered path and extract the max DSM value.
        Returns a DataFrame with checkpoint centroids and max elevation.
        """
        checkpoints = []
        
        coords = ordered_features.geometry.apply(lambda geom: (geom.x, geom.y)).tolist()
        crs = ordered_features.crs
        
        for i in range(len(coords) - 1):
            line = LineString([coords[i], coords[i+1]])
            # buffer = gpd.GeoSeries([line], crs=crs).buffer(self.buffer_path)
            buffer_gdf = gpd.GeoDataFrame(geometry=[line], crs=crs).buffer(self.buffer_path)
            buffer_gdf = gpd.GeoDataFrame(geometry=buffer_gdf, crs=crs)
            # Use zonal_stats to get max elevation in buffer
            stats = zonal_stats(buffer_gdf, self.dsm_path, stats=["max"])
            max_elev = stats[0]["max"]
            # Get centroid of buffer for checkpoint
            centroid = buffer_gdf.centroid.iloc[0]
            checkpoints.append({
                "point_id": 0,
                "type": "cpt",
                "geometry": centroid,
                "elev": max_elev,
                "order": 0
            })
        
        # Return as GeoDataFrame
        gdf_checkpoints = gpd.GeoDataFrame(checkpoints, crs=crs)
        return gdf_checkpoints
    
    # -------------------------------------------------------------------------
    def merge_waypoints_and_checkpoints(self, waypoints, checkpoints):
        """
        Interleave waypoints and checkpoints for CSV export, assigning type 'wpt' and 'cpt'.
        Returns a DataFrame with all points in the correct order.
        """     
        # Interleave: wpt, cpt, wpt, cpt, ..., wpt (last)
        merged = []
        
        for i in range(len(checkpoints)):
            merged.append(waypoints.iloc[i])
            merged.append(checkpoints.iloc[i])
        
        merged.append(waypoints.iloc[-1])
        merged_df = pd.DataFrame(merged)
        
        return merged_df
    
    # -------------------------------------------------------------------------
    def export_to_gpkg(self, gdf, output_path):
        """
        Export a GeoDataFrame to a GPKG file.
        """
        gdf.to_file(output_path, driver="GPKG", mode="w")
        print(f"Exported {len(gdf)} features to {output_path}")
    
    # -------------------------------------------------------------------------
    def export_to_csv(self, df, output_path):
        """
        Export a DataFrame to CSV in the specified folder, naming the file after the feature file.
        """
        df.to_csv(output_path, index=False)
        print(f"Exported {len(df)} rows to {output_path}")
    
    # -------------------------------------------------------------------------
    def to_wgs84(self, gdf):
        """
        Transform a GeoDataFrame to WGS84 (EPSG:4326).
        """
        return gdf.to_crs(epsg=4326)
