from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from rasterstats import zonal_stats
from shapely.geometry import LineString, Point, box


class BuildCSV:
    # -------------------------------------------------------------------------
    def __init__(
        self,
        features_path,
        dsm_path,
        aoi_path=None,
        aoi_index=None,
        aoi_qualifier=None,
        buffer_path=10,
        buffer_feature=3,
        takeoff_coords=None,
        takeoff_coords_projected=False,
        tsp_time_limit_seconds=30,
        crowns_path=None,
        intra_tree_buffer_path=3,
    ):
        self.features_path = features_path
        self.dsm_path = dsm_path
        self.aoi_path = aoi_path
        self.aoi_index = aoi_index
        self.aoi_qualifier = aoi_qualifier
        self.buffer_path = buffer_path
        self.buffer_feature = buffer_feature
        self.takeoff_coords = takeoff_coords
        self.takeoff_coords_projected = takeoff_coords_projected
        self.tsp_time_limit_seconds = tsp_time_limit_seconds
        self.crowns_path = crowns_path
        self.intra_tree_buffer_path = intra_tree_buffer_path

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
        # 5b. Intra-tree mode: assign each point its crown
        if self.crowns_path is not None:
            features = self.assign_crowns(features)
        # 6. Build distance matrix and get coordinates
        coords = np.array([[geom.x, geom.y] for geom in features.geometry])
        distance_matrix = self.build_distance_matrix(features.geometry.tolist())
        # 7. Transform takeoff coordinates to DSM CRS if needed
        takeoff_coords_dsm = None
        if self.takeoff_coords is not None:
            takeoff_coords_dsm = self.transform_takeoff_coords_to_dsm_crs(
                self.takeoff_coords, dsm.crs
            )
        # 8. Solve TSP (optionally with takeoff site)
        tsp_route = self.solve_tsp_ortools(
            distance_matrix,
            takeoff_coords=takeoff_coords_dsm,
            waypoints_coords=coords,
            time_limit_seconds=self.tsp_time_limit_seconds,
            groups=features["crown_id"].tolist() if self.crowns_path is not None else None,
        )
        # 9. Reorder features according to TSP
        waypoints = self.get_tsp_solution_df(features, tsp_route)
        # 10. Extract path checkpoints
        checkpoints = self.extract_path_checkpoints(waypoints)
        # 11. Interleave waypoints and checkpoints
        merged = self.merge_waypoints_and_checkpoints(waypoints, checkpoints)
        merged = self.fix_cpt_wpt_elevation_duplicates(merged)
        # 12. Transform to WGS84 for export
        merged_gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs=features.crs)
        merged_gdf = self.to_wgs84(merged_gdf)
        # 13. Format for CSV: extract lon/lat, rename columns, drop geometry
        merged_gdf["lon_x"] = merged_gdf.geometry.x
        merged_gdf["lat_y"] = merged_gdf.geometry.y
        # Add placeholder columns if missing
        if "cluster_id" not in merged_gdf:
            merged_gdf["cluster_id"] = 0
        merged_gdf["elevation_from_dsm"] = merged_gdf["elev"]
        gpkg_gdf = merged_gdf.drop(columns=["elevation_from_dsm"])
        gpkg_gdf = gpkg_gdf[gpkg_gdf["type"] != "cpt"]
        csv_columns = [
            "point_id",
            "cluster_id",
            "type",
            "lon_x",
            "lat_y",
            "elevation_from_dsm",
            "order",
        ]
        if self.crowns_path is not None:
            csv_columns.insert(2, "crown_id")
        csv_df = merged_gdf[csv_columns]
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
        features = gpd.read_file(self.features_path, engine="pyogrio", fid_as_index=True)

        # Check geometry type
        geom_type = features.geometry.geom_type.unique()
        if self.crowns_path is not None and not all(gt == "Point" for gt in geom_type):
            raise ValueError(
                f"Intra-tree mode (crowns_path) needs point features, found {list(geom_type)}. "
                "Give the photo points as features and the crown polygons as crowns_path."
            )
        if all(gt in ["Polygon", "MultiPolygon"] for gt in geom_type):
            # Convert polygons to centroids
            # features['geometry'] = features.centroid
            # or use representative_point() if you want a point inside the polygon
            features["geometry"] = features.geometry.representative_point()
        elif all(gt == "Point" for gt in geom_type):
            pass
        else:
            raise ValueError(
                f"Unsupported geometry type(s): {geom_type}. Input features file should contain only Polygon, MultiPolygon or Point geometries."
            )

        # Add 'point_id' column if missing
        if "point_id" not in features.columns:
            features["point_id"] = features["FID"] if "FID" in features.columns else features.index

        # If AOI is provided, filter features
        if self.aoi_path is not None:
            aoi = gpd.read_file(self.aoi_path)
            # Select AOI by index (1-based) or by qualifier attribute
            if self.aoi_index is not None:
                aoi = aoi.iloc[[self.aoi_index - 1]]  # 1-based index
            elif self.aoi_qualifier is not None:
                if "qualifier" not in aoi.columns:
                    raise ValueError(
                        f"AOI file does not contain a 'qualifier' column. "
                        f"Cannot select AOI by qualifier='{self.aoi_qualifier}'."
                    )
                aoi = aoi[aoi["qualifier"] == self.aoi_qualifier]
                if aoi.empty:
                    raise ValueError(f"No AOI feature found with qualifier='{self.aoi_qualifier}'.")
            # Ensure CRS matches
            if features.crs != aoi.crs:
                print(
                    f"Warning: AOI CRS ({aoi.crs}) does not match features CRS ({features.crs}). Reprojecting AOI to features CRS."
                )
                aoi = aoi.to_crs(features.crs)

            mask = features.geometry.intersects(aoi.unary_union)
            features = features[mask]

        # Validate feature count: at least 2 features needed for route planning
        num_features = len(features)
        if num_features == 0:
            raise ValueError(
                f"No features found in '{self.features_path}'. Ensure the input features file contains at least 2 features."
            )
        if num_features == 1:
            # include point_id if present
            single_id = None
            try:
                single_id = features.iloc[0].get("point_id", None)
            except Exception:
                single_id = None
            id_msg = f" (point_id={single_id})" if single_id is not None else ""
            raise ValueError(
                f"Features file must contain at least 2 features for route planning. Found only 1 feature{id_msg}."
            )

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
            print(
                f"Warning: Features CRS ({features.crs}) does not match DSM CRS ({dsm_crs}). Reprojecting features to DSM CRS."
            )
            features = features.to_crs(dsm_crs)
        # Distances and buffers below assume metres. A geographic DSM CRS
        # (degrees) silently truncates the x1000-scaled distance matrix to zero
        # integers, yielding an arbitrary TSP route. Fail loud instead.
        if features.crs is not None and not features.crs.is_projected:
            raise ValueError(
                f"DSM CRS ({dsm_crs}) is geographic (degrees). A projected CRS "
                "(e.g. UTM) is required so distances and buffers are in metres. "
                "Reproject the DSM to a projected CRS and retry."
            )
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
            ids_outside = non_overlapping_features["point_id"].tolist()
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
        # zonal_stats returns max=None where a buffer falls entirely on DSM
        # nodata (extent edge / hole). Left unguarded, None flows to the CSV as
        # "None" and later float("None") crashes mission generation. Fail loud.
        missing = [features.iloc[i].get("point_id", i) for i, v in enumerate(max_elev) if v is None]
        if missing:
            raise ValueError(
                f"DSM has no data under {len(missing)} feature buffer(s) "
                f"(point_id {missing[:10]}). Increase DSM coverage or reduce buffer_feature."
            )
        features = features.copy()
        features["elev"] = max_elev
        return features

    # -------------------------------------------------------------------------
    def read_crowns(self, crs):
        """Read the crown polygons, with a unique 'crown_id', in the given CRS."""
        crowns = gpd.read_file(self.crowns_path, engine="pyogrio", fid_as_index=True)

        geom_type = crowns.geometry.geom_type.unique()
        if not all(gt in ["Polygon", "MultiPolygon"] for gt in geom_type):
            raise ValueError(
                f"Unsupported crown geometry type(s): {list(geom_type)}. "
                "The crowns file should contain only Polygon or MultiPolygon geometries."
            )

        if "crown_id" not in crowns.columns:
            crowns["crown_id"] = crowns["FID"] if "FID" in crowns.columns else crowns.index

        if crowns["crown_id"].isna().any():
            raise ValueError("Some crowns have no crown_id. Every crown needs one.")
        duplicated = crowns.loc[crowns["crown_id"].duplicated(), "crown_id"].unique().tolist()
        if duplicated:
            raise ValueError(
                f"crown_id must be unique across crowns. Duplicated: {duplicated[:10]}"
            )

        if crowns.crs != crs:
            print(
                f"Warning: Crowns CRS ({crowns.crs}) does not match DSM CRS ({crs}). "
                "Reprojecting crowns to DSM CRS."
            )
            crowns = crowns.to_crs(crs)
        return crowns[["crown_id", "geometry"]]

    # -------------------------------------------------------------------------
    def assign_crowns(self, features):
        """Add a 'crown_id' column, None for points outside every crown."""
        crowns = self.read_crowns(features.crs)

        points = features[["point_id", "geometry"]].reset_index(drop=True)
        joined = gpd.sjoin(points, crowns, how="left", predicate="intersects")

        counts = joined.index.value_counts()
        ambiguous = counts[counts > 1].index
        if len(ambiguous) > 0:
            ids = points.loc[ambiguous, "point_id"].tolist()
            raise ValueError(
                f"{len(ids)} point(s) fall inside more than one crown (point_id {ids[:10]}). "
                "Fix the overlapping crowns and retry."
            )

        crown_ids = joined["crown_id"].astype(object)
        crown_ids = crown_ids.where(crown_ids.notna(), None)

        features = features.copy()
        features["crown_id"] = crown_ids.to_numpy()

        in_crown = features["crown_id"].notna()
        sizes = features.loc[in_crown, "crown_id"].value_counts()
        print(
            f"Intra-tree mode: {int(in_crown.sum())} of {len(features)} points fall in "
            f"{len(sizes)} crown(s), {int((sizes > 1).sum())} of them with several points. "
            f"{int((~in_crown).sum())} point(s) outside every crown are flown as standalone "
            "features."
        )
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
                crs="EPSG:4326",
            )
            point_dsm_crs = point_wgs84.to_crs(dsm_crs)
            transformed_coords = [
                point_dsm_crs.geometry.iloc[0].x,
                point_dsm_crs.geometry.iloc[0].y,
            ]
            print(
                f"Transformed takeoff coordinates from WGS84 [lat, lon] {takeoff_coords} to {dsm_crs} [x, y] {transformed_coords}"
            )
            return transformed_coords
        else:
            # Coordinates are already in DSM CRS (projected) as [x, y]
            print(f"Using takeoff coordinates [x, y] {takeoff_coords} (assumed to be in DSM CRS)")
            return takeoff_coords

    # -------------------------------------------------------------------------
    @staticmethod
    def solve_tsp_ortools(
        distance_matrix,
        takeoff_coords=None,
        waypoints_coords=None,
        time_limit_seconds=30,
        groups=None,
    ):
        """
        Solve TSP using Google OR-Tools. Scales distances by 1000 to use integers.
        If takeoff_coords and waypoints_coords are provided, use takeoff site as the start and find the nearest waypoint.
        `groups` (crown_id or None per node) keeps each group's nodes consecutive.
        """
        # Scale the distance matrix by 1000 and convert to int
        scaled_matrix = (distance_matrix * 1000).astype(np.int64)

        start_index = 0
        if takeoff_coords is not None and waypoints_coords is not None:
            # Compute distances from takeoff site to all waypoints
            takeoff = np.array(takeoff_coords)
            dists = np.linalg.norm(waypoints_coords - takeoff, axis=1)
            start_index = int(np.argmin(dists))
        manager = pywrapcp.RoutingIndexManager(len(scaled_matrix), 1, start_index)
        routing = pywrapcp.RoutingModel(manager)

        if groups is not None:
            scaled_matrix = BuildCSV.group_penalized_matrix(scaled_matrix, groups, start_index)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(scaled_matrix[from_node][to_node])

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Set search parameters
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_parameters.time_limit.seconds = time_limit_seconds
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
            if groups is not None:
                BuildCSV.check_groups_contiguous(route, groups)
            return route
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def group_penalized_matrix(scaled_matrix, groups, start_index):
        """
        Penalize arcs between groups by more than any route length, so each group
        is entered once. Arcs back to the start are penalized too, so the start
        group is not split between both ends of the closed route.
        """
        n = len(scaled_matrix)
        labels = [
            ("node", i) if BuildCSV.is_missing(g) else ("group", g) for i, g in enumerate(groups)
        ]
        penalty = int(scaled_matrix.max()) * n + 1
        penalized = scaled_matrix.copy()
        for i in range(n):
            for j in range(n):
                if i != j and (labels[i] != labels[j] or j == start_index):
                    penalized[i][j] += penalty
        return penalized

    # -------------------------------------------------------------------------
    @staticmethod
    def check_groups_contiguous(route, groups):
        """Raise if the route leaves a group and comes back to it later."""
        seen = set()
        previous = None
        for node in route:
            g = groups[node]
            if BuildCSV.is_missing(g):
                previous = None
                continue
            if g != previous and g in seen:
                raise ValueError(
                    f"The route visits crown {g!r} in more than one pass. "
                    "Increase tsp_time_limit_seconds and retry."
                )
            seen.add(g)
            previous = g

    # -------------------------------------------------------------------------
    @staticmethod
    def is_missing(value):
        return value is None or (not isinstance(value, str) and pd.isna(value))

    # -------------------------------------------------------------------------
    @staticmethod
    def same_crown(a, b):
        if BuildCSV.is_missing(a) or BuildCSV.is_missing(b):
            return False
        return a == b

    # -------------------------------------------------------------------------
    def get_tsp_solution_df(self, features, route):
        """
        Given a list of feature indices (route), return a DataFrame with the features in TSP order and an 'order' column.
        """
        # Reorder features according to the TSP route
        ordered_features = features.iloc[route].copy()
        ordered_features["order"] = range(1, len(route) + 1)
        ordered_features["type"] = "wpt"
        cols = ["point_id", "type", "geometry", "elev", "order"]
        if "crown_id" in ordered_features.columns:
            cols.append("crown_id")
        ordered_features = ordered_features[cols]
        return ordered_features

    # -------------------------------------------------------------------------
    def extract_path_checkpoints(self, ordered_features):
        """
        For each consecutive pair of waypoints, create a buffered path and extract the max DSM value.
        Returns a DataFrame with checkpoint centroids and max elevation.
        Between two waypoints of the same crown, samples intra_tree_buffer_path
        around the path plus buffer_feature around each waypoint instead.
        """
        checkpoints = []

        coords = ordered_features.geometry.apply(lambda geom: (geom.x, geom.y)).tolist()
        crs = ordered_features.crs
        intra_tree = "crown_id" in ordered_features.columns
        crown_ids = ordered_features["crown_id"].tolist() if intra_tree else None
        elevations = ordered_features["elev"].tolist()

        for i in range(len(coords) - 1):
            line = LineString([coords[i], coords[i + 1]])
            crown_id = None
            if intra_tree and self.same_crown(crown_ids[i], crown_ids[i + 1]):
                crown_id = crown_ids[i]
                area = (
                    line.buffer(self.intra_tree_buffer_path)
                    .union(Point(coords[i]).buffer(self.buffer_feature))
                    .union(Point(coords[i + 1]).buffer(self.buffer_feature))
                )
                buffer_name = "intra_tree_buffer_path"
            else:
                area = line.buffer(self.buffer_path)
                buffer_name = "buffer_path"
            buffer_gdf = gpd.GeoDataFrame(geometry=[area], crs=crs)
            # Use zonal_stats to get max elevation in buffer
            stats = zonal_stats(buffer_gdf, self.dsm_path, stats=["max"])
            max_elev = stats[0]["max"]
            if max_elev is None:
                raise ValueError(
                    f"DSM has no data under the path buffer between waypoints {i} and "
                    f"{i + 1}. Increase DSM coverage or reduce {buffer_name}."
                )
            if crown_id is not None:
                max_elev = max(max_elev, elevations[i], elevations[i + 1])
            # Get centroid of buffer for checkpoint
            centroid = buffer_gdf.centroid.iloc[0]
            checkpoint = {
                "point_id": 0,
                "type": "cpt",
                "geometry": centroid,
                "elev": max_elev,
                "order": 0,
            }
            if intra_tree:
                checkpoint["crown_id"] = crown_id
            checkpoints.append(checkpoint)

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
        Intra-tree checkpoints are skipped: placemark_plan drops duplicates instead.
        """
        merged_df = merged_df.reset_index(drop=True)

        for i in range(len(merged_df) - 1):
            curr = merged_df.iloc[i]
            next_ = merged_df.iloc[i + 1]
            if "crown_id" in merged_df.columns and not self.is_missing(curr["crown_id"]):
                continue
            if (
                curr["type"] == "cpt"
                and next_["type"] == "wpt"
                and abs(curr["elev"] - next_["elev"]) < 1e-3
            ):
                merged_df.iloc[i, merged_df.columns.get_loc("elev")] = curr["elev"] + 1

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
