import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import re

from ortools.constraint_solver import routing_enums_pb2, pywrapcp
from pathlib import Path
from rasterstats import zonal_stats
from shapely.geometry import box, LineString, Point

class BuildCSV:
    # -------------------------------------------------------------------------
    def __init__(self, features_path, dsm_path, aoi_path=None, aoi_index=1, aoi_qualifier="", buffer_path=10, buffer_feature=3, takeoff_coords=None, takeoff_coords_projected=False):
        self.features_path = features_path
        self.dsm_path = dsm_path
        self.aoi_path = aoi_path
        self.aoi_index = aoi_index
        self.aoi_qualifier = aoi_qualifier
        self.buffer_path = buffer_path
        self.buffer_feature = buffer_feature
        self.takeoff_coords = takeoff_coords
        self.takeoff_coords_projected = takeoff_coords_projected
    
    # -------------------------------------------------------------------------
    def run(self, output_folder, output_filename):
        """
        Full workflow: process features, DSM, TSP, checkpoints, and export results.
        """
        # 1. Read features (with AOI filtering if provided)
        features = self.read_features()
        # 2. Read DSM raster
        dsm = self.read_dsm()
        # 3. Align CRS (if needed)
        features = self.align_features_to_dsm(features, dsm)
        # 4. Check for overlap
        self.check_features_overlap_dsm(features, dsm)
        # 5. Extract feature elevations
        features = self.extract_features_elevations(features)
        # 6. Build distance matrix and get coordinates
        coords = np.array([[geom.x, geom.y] for geom in features.geometry])
        distance_matrix = self.build_distance_matrix(features.geometry.tolist())
        # 7. Transform takeoff coordinates to DSM CRS if needed
        takeoff_coords_dsm = None
        if self.takeoff_coords is not None:
            takeoff_coords_dsm = self.transform_takeoff_coords_to_dsm_crs(self.takeoff_coords, dsm.crs)
        # 8. Solve TSP (optionally with takeoff site)
        tsp_route = self.solve_tsp_ortools(distance_matrix, takeoff_coords=takeoff_coords_dsm, waypoints_coords=coords)
        # 9. Reorder features according to TSP
        waypoints = self.get_tsp_solution_df(features, tsp_route)
        # 10. Extract path checkpoints
        checkpoints = self.extract_path_checkpoints(waypoints)
        # 11. Interleave waypoints and checkpoints
        merged = self.merge_waypoints_and_checkpoints(waypoints, checkpoints)
        merged = self.fix_cpt_wpt_elevation_duplicates(merged)
        # 12. Transform to WGS84 for export
        merged_gdf = gpd.GeoDataFrame(merged, geometry='geometry', crs=features.crs)
        merged_gdf = self.to_wgs84(merged_gdf)
        # 13. Format for CSV: extract lon/lat, rename columns, drop geometry
        merged_gdf['lon_x'] = merged_gdf.geometry.x
        merged_gdf['lat_y'] = merged_gdf.geometry.y
        # Add placeholder columns if missing
        if 'cluster_id' not in merged_gdf:
            merged_gdf['cluster_id'] = 0
        merged_gdf['elevation_from_dsm'] = merged_gdf['elev']
        gpkg_gdf = merged_gdf.drop(columns=['elevation_from_dsm'])
        gpkg_gdf = gpkg_gdf[gpkg_gdf['type'] != 'cpt']
        csv_df = merged_gdf[['point_id', 'cluster_id', 'type', 'lon_x', 'lat_y', 'elevation_from_dsm', 'order']]
        # 14. Export
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)  # Create directory if it doesn't exist
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
        
        # Validate feature count: at least 2 features needed for route planning
        num_features = len(features)
        if num_features == 0:
            raise ValueError(f"No features found in '{self.features_path}'. Ensure the input features file contains at least 2 features.")
        if num_features == 1:
            # include point_id if present
            single_id = None
            try:
                single_id = features.iloc[0].get('point_id', None)
            except Exception:
                single_id = None
            id_msg = f" (point_id={single_id})" if single_id is not None else ""
            raise ValueError(f"Features file must contain at least 2 features for route planning. Found only 1 feature{id_msg}.")

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
    def check_features_overlap_dsm(self, features, dsm):
        """
        Check if all features are within the DSM's bounding box.
        Raises a ValueError if any feature is outside the DSM bounds.
        """
        dsm_bounds = dsm.bounds
        dsm_box = box(dsm_bounds.left, dsm_bounds.bottom, dsm_bounds.right, dsm_bounds.top)
        
        # Check which features are not within the DSM box
        non_overlapping_features = features[~features.geometry.within(dsm_box)]
        
        if not non_overlapping_features.empty:
            num_outside = len(non_overlapping_features)
            total_num = len(features)
            # List some of the non-overlapping feature IDs
            ids_outside = non_overlapping_features['point_id'].tolist()
            error_message = (
                f"{num_outside} out of {total_num} features are outside the DSM extent.\n"
                f"Non-overlapping feature IDs: {ids_outside[:10]}"
            )
            if num_outside > 10:
                error_message += " (and others)..."
            raise ValueError(error_message)
    
    # -------------------------------------------------------------------------
    def extract_features_elevations(self, features):
        """
        For each feature, create a buffer and extract the DSM elevation value. Returns a GeoDataFrame with an 'elev' column.
        """
        # Create buffer around centroids
        buffers = features.buffer(self.buffer_feature)
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
    def transform_takeoff_coords_to_dsm_crs(self, takeoff_coords, dsm_crs):
        """
        Transform takeoff coordinates to DSM CRS if needed.
        If takeoff_coords_projected=False (default), assumes WGS84 (lat, lon) and transforms to DSM CRS.
        If takeoff_coords_projected=True, assumes coordinates (y, x) are already in DSM CRS.
        """
        if not self.takeoff_coords_projected:
            # Coordinates are in WGS84 (lat, lon), transform to DSM CRS
            lat, lon = takeoff_coords[0], takeoff_coords[1]
            point_wgs84 = gpd.GeoDataFrame(
                geometry=[Point(lon, lat)],  # Point expects (x, y) which is (lon, lat)
                crs="EPSG:4326"
            )
            point_dsm_crs = point_wgs84.to_crs(dsm_crs)
            transformed_coords = [point_dsm_crs.geometry.iloc[0].x, point_dsm_crs.geometry.iloc[0].y]
            print(f"Transformed takeoff coordinates from WGS84 [lat, lon] {takeoff_coords} to {dsm_crs} [x, y] {transformed_coords}")
            return transformed_coords
        else:
            # Coordinates are already in DSM CRS (projected) as [x, y]
            print(f"Using takeoff coordinates [x, y] {takeoff_coords} (assumed to be in DSM CRS)")
            return takeoff_coords
    
    # -------------------------------------------------------------------------
    @staticmethod
    def solve_tsp_ortools(distance_matrix, takeoff_coords=None, waypoints_coords=None):
        """
        Solve TSP using Google OR-Tools. Scales distances by 1000 to use integers.
        If takeoff_coords and waypoints_coords are provided, use takeoff site as the start and find the nearest waypoint.
        """
        # Scale the distance matrix by 1000 and convert to int
        scaled_matrix = (distance_matrix * 1000).astype(int)
        
        start_index = 0
        if takeoff_coords is not None and waypoints_coords is not None:
            # Compute distances from takeoff site to all waypoints
            takeoff = np.array(takeoff_coords)
            dists = np.linalg.norm(waypoints_coords - takeoff, axis=1)
            start_index = int(np.argmin(dists))
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
    def fix_cpt_wpt_elevation_duplicates(self, merged_df):
        """
        Fix pause mission error when a checkpoint is immediately followed by a waypoint with the same elevation.
        Adds +1 to the checkpoint elevation to avoid the conflict.
        """
        merged_df = merged_df.reset_index(drop=True)

        for i in range(len(merged_df) - 1):
            curr = merged_df.iloc[i]
            next_ = merged_df.iloc[i + 1]
            if (
                curr['type'] == 'cpt' and
                next_['type'] == 'wpt' and
                abs(curr['elev'] - next_['elev']) < 1e-3
            ):
                merged_df.iloc[i, merged_df.columns.get_loc('elev')] = curr['elev'] + 1
        
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
    
    # -------------------------------------------------------------------------
    def to_wgs84(self, gdf):
        """
        Transform a GeoDataFrame to WGS84 (EPSG:4326).
        """
        return gdf.to_crs(epsg=4326)
