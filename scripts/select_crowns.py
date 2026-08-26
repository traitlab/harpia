"""
select_crowns.py

Filter candidate tree crowns to a shortlist suitable for close-up drone missions.

Five independent filters are available. Each one is OPTIONAL and runs only when
its input is supplied (on the command line or in a YAML config file):

  1. AOI          : keep crowns inside an area-of-interest polygon    (--aoi)
  2. Area         : keep crowns at or above a minimum area            (--min-area)
  3. Visited      : drop crowns that already contain a waypoint       (--waypoints)
  4. Already known: drop crowns overlapping a reference layer         (--exclude)
  5. DSM relief   : drop crowns whose surroundings are much taller    (--dsm)
                    than the crown itself

Filters are applied in the order above; each one operates on the survivors of
the previous one.

Example
-------
    python scripts/select_crowns.py \
        --crowns crowns.gpkg \
        --output selected_crowns.gpkg \
        --aoi drone_sites.gpkg --site-id bcipearson \
        --min-area 25 \
        --waypoints 2024_bci_wpt.gpkg \
        --exclude predictions_above80.gpkg \
        --dsm Sept2025DSM_Plus_25m_Towers_v2.tif --buffer-large 8 --buffer-small 1 --max-dsm-diff 5

    python scripts/select_crowns.py --config config/select_crowns.yaml

Any subset of the filter arguments may be omitted, in which case the
corresponding step is skipped.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import yaml
from rasterstats import zonal_stats

# Defaults for every setting. A YAML config overrides these, and command-line
# arguments override the YAML config.
DEFAULTS = {
    # Input / output
    "crowns_path": None,  # required: candidate crowns (polygons)
    "output_path": None,  # required: destination for the selected crowns
    "overwrite": False,  # allow an existing output file to be replaced
    # Filter 1 - AOI
    "aoi_path": None,  # enables the filter
    "site_field": "site_id",  # attribute used to pick one site in the AOI layer
    "site_id": None,  # value to match; None keeps every AOI feature
    "aoi_predicate": "within",  # 'within' (fully inside) or 'intersects'
    # Filter 2 - minimum area
    "min_area": None,  # enables the filter; square metres
    "area_field": None,  # use this column instead of the computed geometry area
    # Filter 3 - already visited
    "waypoints_path": None,  # enables the filter
    # Filter 4 - already known species
    "exclude_path": None,  # enables the filter
    # Filter 5 - DSM relief
    "dsm_path": None,  # enables the filter
    "buffer_large": 8.0,  # outer buffer radius around the centroid (m)
    "buffer_small": 1.0,  # inner buffer radius around the centroid (m)
    "max_dsm_diff": 5.0,  # max allowed (outer max - inner max) elevation (m)
    "dsm_nodata": None,  # override the raster's declared nodata value
    "keep_undetermined": False,  # keep crowns the DSM cannot evaluate
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def to_metric(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return *gdf* in a CRS whose units are metres, reprojecting if needed."""
    if gdf.crs is None:
        raise ValueError("Layer has no CRS; cannot measure distances or areas.")
    if gdf.crs.is_projected:
        return gdf
    return gdf.to_crs(gdf.estimate_utm_crs())


def read_aligned(path: str | Path, crs, columns: list[str] | None = None) -> gpd.GeoDataFrame:
    """Read a vector layer and reproject it to *crs*."""
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError(f"'{path}' has no CRS; cannot align it with the crowns layer.")
    gdf = gdf.to_crs(crs)
    return gdf[columns] if columns else gdf


def report(step: str, before: int, after: int, note: str = "") -> None:
    suffix = f"  {note}" if note else ""
    print(f"  {step:<22}: {after:>7} kept  ({before - after} removed){suffix}")


def skipped(step: str, reason: str) -> None:
    print(f"  {step:<22}: skipped ({reason})")


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def filter_by_aoi(
    crowns: gpd.GeoDataFrame,
    aoi_path: str,
    site_field: str,
    site_id: str | None,
    predicate: str,
) -> gpd.GeoDataFrame:
    """Keep crowns located inside the AOI polygon(s)."""
    aoi = read_aligned(aoi_path, crowns.crs)

    if site_id is not None:
        if site_field not in aoi.columns:
            raise ValueError(
                f"AOI layer '{aoi_path}' has no '{site_field}' column "
                f"(available: {', '.join(aoi.columns)})"
            )
        aoi = aoi[aoi[site_field].astype(str) == str(site_id)]
        if aoi.empty:
            raise ValueError(f"No AOI feature found with {site_field} = '{site_id}'")

    # Union so that a site split across several polygons is handled correctly.
    aoi_geom = aoi.geometry.union_all()
    mask = crowns.within(aoi_geom) if predicate == "within" else crowns.intersects(aoi_geom)
    return crowns[mask]


def filter_by_area(
    crowns: gpd.GeoDataFrame, min_area: float, area_field: str | None
) -> gpd.GeoDataFrame:
    """Keep crowns whose area is at least *min_area* square metres."""
    if area_field:
        if area_field not in crowns.columns:
            raise ValueError(f"Crowns layer has no '{area_field}' column.")
        area = pd.to_numeric(crowns[area_field], errors="coerce")
    else:
        # Computed from the geometry so the script does not depend on the
        # presence of a pre-existing area attribute.
        area = to_metric(crowns).geometry.area
    return crowns[area >= min_area]


def exclude_by_overlap(
    crowns: gpd.GeoDataFrame, other_path: str, predicate: str
) -> gpd.GeoDataFrame:
    """Drop crowns matching *predicate* against any feature of *other_path*."""
    other = read_aligned(other_path, crowns.crs, columns=["geometry"])
    if other.empty:
        return crowns
    hits = crowns.sjoin(other, how="inner", predicate=predicate).index.unique()
    return crowns.loc[~crowns.index.isin(hits)]


def zonal_max(geoms: gpd.GeoSeries, dsm_path: str, nodata: float | None) -> pd.Series:
    """Maximum DSM value under each geometry, NaN where it cannot be computed."""
    stats = zonal_stats(
        list(geoms),
        dsm_path,
        stats=["max"],
        all_touched=True,  # small buffers may not cover a single pixel centre
        nodata=nodata,
        boundless=True,  # geometries partly outside the raster do not raise
    )
    values = [s.get("max") if s else None for s in stats]
    series = pd.to_numeric(pd.Series(values, index=geoms.index), errors="coerce")
    return series.replace([np.inf, -np.inf], np.nan)


def filter_by_dsm(
    crowns: gpd.GeoDataFrame,
    dsm_path: str,
    buffer_large: float,
    buffer_small: float,
    max_diff: float,
    nodata: float | None,
    keep_undetermined: bool,
) -> tuple[gpd.GeoDataFrame, int]:
    """Drop crowns overtopped by their surroundings according to the DSM.

    For each crown centroid, the maximum DSM elevation in a large buffer is
    compared with the maximum in a small buffer. A large positive difference
    means a taller neighbour dominates the crown.
    """
    metric = to_metric(crowns)
    centroids = metric.geometry.centroid

    with rasterio.open(dsm_path) as dsm:
        dsm_crs = dsm.crs
        if nodata is None:
            nodata = dsm.nodata
    if dsm_crs is None:
        raise ValueError(f"DSM '{dsm_path}' has no CRS.")

    # Buffers are built in the metric CRS (so the radii really are metres),
    # then reprojected to the raster CRS in one vectorised operation.
    large = centroids.buffer(buffer_large)
    small = centroids.buffer(buffer_small)
    if dsm_crs != metric.crs:
        large = large.to_crs(dsm_crs)
        small = small.to_crs(dsm_crs)

    diff = zonal_max(large, dsm_path, nodata) - zonal_max(small, dsm_path, nodata)

    undetermined = diff.isna()
    keep = diff <= max_diff
    if keep_undetermined:
        keep = keep | undetermined

    return crowns[keep.reindex(crowns.index, fill_value=False)], int(undetermined.sum())


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Filter candidate tree crowns for close-up drone missions. "
            "Every filter is optional and runs only when its input is provided."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", "-c", help="Path to a YAML configuration file.")

    io_group = parser.add_argument_group("input/output")
    io_group.add_argument("--crowns", "-i", dest="crowns_path", help="Candidate crowns layer.")
    io_group.add_argument("--output", "-o", dest="output_path", help="Selected crowns layer.")
    io_group.add_argument(
        "--overwrite",
        action="store_true",
        default=None,
        help="Replace the output file if it already exists.",
    )

    aoi = parser.add_argument_group("filter 1 - area of interest (optional)")
    aoi.add_argument("--aoi", dest="aoi_path", help="AOI polygon layer; enables the AOI filter.")
    aoi.add_argument("--site-field", help="AOI attribute holding the site identifier.")
    aoi.add_argument("--site-id", help="Site value to select; default keeps all AOI features.")
    aoi.add_argument(
        "--aoi-predicate",
        choices=["within", "intersects"],
        help="Require crowns to be fully inside the AOI, or merely to touch it.",
    )

    area = parser.add_argument_group("filter 2 - minimum area (optional)")
    area.add_argument(
        "--min-area", type=float, help="Minimum crown area in m2; enables the area filter."
    )
    area.add_argument("--area-field", help="Use this column instead of the geometry area.")

    visited = parser.add_argument_group("filter 3 - already visited (optional)")
    visited.add_argument(
        "--waypoints",
        dest="waypoints_path",
        help="Waypoints layer; crowns containing a waypoint are dropped.",
    )

    known = parser.add_argument_group("filter 4 - already known crowns (optional)")
    known.add_argument(
        "--exclude",
        dest="exclude_path",
        help="Reference layer; crowns intersecting any of its features are dropped.",
    )

    dsm = parser.add_argument_group("filter 5 - DSM relief (optional)")
    dsm.add_argument("--dsm", dest="dsm_path", help="DSM raster; enables the relief filter.")
    dsm.add_argument("--buffer-large", type=float, help="Outer buffer radius (m).")
    dsm.add_argument("--buffer-small", type=float, help="Inner buffer radius (m).")
    dsm.add_argument(
        "--max-dsm-diff", type=float, help="Maximum tolerated elevation difference (m)."
    )
    dsm.add_argument("--dsm-nodata", type=float, help="Override the raster's nodata value.")
    dsm.add_argument(
        "--keep-undetermined",
        action="store_true",
        default=None,
        help="Keep crowns whose DSM statistics cannot be computed (default: drop them).",
    )
    return parser


def resolve_settings(argv: list[str] | None = None) -> dict:
    """Merge defaults, YAML config and command-line arguments (in that order)."""
    args = build_parser().parse_args(argv)
    settings = dict(DEFAULTS)

    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        unknown = set(loaded) - set(DEFAULTS)
        if unknown:
            raise ValueError(f"Unknown settings in {config_path}: {', '.join(sorted(unknown))}")
        settings.update({k: v for k, v in loaded.items() if v is not None})

    cli = {k: v for k, v in vars(args).items() if k != "config" and v is not None}
    settings.update(cli)

    for key in ("crowns_path", "output_path"):
        if not settings[key]:
            raise ValueError(f"'{key}' is required (--{key.replace('_path', '')} or config file).")
    return settings


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def select_crowns(settings: dict) -> gpd.GeoDataFrame:
    """Apply every enabled filter and return the surviving crowns."""
    print(f"Reading crowns from {settings['crowns_path']}")
    crowns = gpd.read_file(settings["crowns_path"])
    if crowns.crs is None:
        raise ValueError("Crowns layer has no CRS.")
    # A unique, stable index is what every filter below relies on.
    candidates = crowns.reset_index(drop=True)
    print(f"  {'total crowns':<22}: {len(candidates):>7}")

    steps = [
        (
            "1. AOI",
            settings["aoi_path"],
            "no --aoi",
            lambda gdf: filter_by_aoi(
                gdf,
                settings["aoi_path"],
                settings["site_field"],
                settings["site_id"],
                settings["aoi_predicate"],
            ),
        ),
        (
            "2. minimum area",
            settings["min_area"],
            "no --min-area",
            lambda gdf: filter_by_area(gdf, settings["min_area"], settings["area_field"]),
        ),
        (
            "3. already visited",
            settings["waypoints_path"],
            "no --waypoints",
            lambda gdf: exclude_by_overlap(gdf, settings["waypoints_path"], "contains"),
        ),
        (
            "4. already known",
            settings["exclude_path"],
            "no --exclude",
            lambda gdf: exclude_by_overlap(gdf, settings["exclude_path"], "intersects"),
        ),
    ]

    for name, enabled_by, reason, run in steps:
        if not enabled_by:
            skipped(name, reason)
        elif candidates.empty:
            skipped(name, "no candidate left")
        else:
            before = len(candidates)
            candidates = run(candidates)
            report(name, before, len(candidates))

    if not settings["dsm_path"]:
        skipped("5. DSM relief", "no --dsm")
    elif candidates.empty:
        skipped("5. DSM relief", "no candidate left")
    else:
        before = len(candidates)
        print(f"  {'5. DSM relief':<22}: evaluating {before} candidates ...")
        candidates, undetermined = filter_by_dsm(
            candidates,
            settings["dsm_path"],
            settings["buffer_large"],
            settings["buffer_small"],
            settings["max_dsm_diff"],
            settings["dsm_nodata"],
            settings["keep_undetermined"],
        )
        fate = "kept" if settings["keep_undetermined"] else "dropped"
        note = f"[{undetermined} without DSM data, {fate}]" if undetermined else ""
        report("5. DSM relief", before, len(candidates), note)

    return candidates


def main(argv: list[str] | None = None) -> int:
    try:
        settings = resolve_settings(argv)
        output_path = Path(settings["output_path"])
        if output_path.exists() and not settings["overwrite"]:
            raise FileExistsError(f"{output_path} already exists; pass --overwrite to replace it.")
        selected = select_crowns(settings)
    except Exception as error:  # noqa: BLE001 - report cleanly instead of a traceback
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if selected.empty:
        print("\nNo crown passed the filters; nothing was written.", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected.to_file(output_path)
    print(f"\nDone. {len(selected)} crowns written to '{output_path}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
