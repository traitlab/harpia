"""Shared pytest fixtures and import-time setup for harpia tests.

``src/lib/config.py`` parses ``sys.argv`` and builds a module-level ``config``
singleton at import time. Tests that import the KML/WPML/KMZ builders therefore
need a valid argv in place before the first import. We inject a minimal CSV-based
invocation here so the config singleton constructs cleanly, then individual tests
mutate the singleton's attributes (output paths, csv_path, drone_model, ...).
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Ensure the repository root is importable (so ``import src.lib...`` resolves)
# regardless of pytest's rootdir handling.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# A CSV that satisfies the FilePath validator at config import time. Lives in the
# repo so it exists before any test runs; contents are irrelevant to config.
_BOOTSTRAP_CSV = REPO_ROOT / "tests" / "_bootstrap.csv"


def _ensure_bootstrap_csv() -> None:
    if not _BOOTSTRAP_CSV.exists():
        _BOOTSTRAP_CSV.write_text("point_id,cluster_id,type,lon_x,lat_y,elevation_from_dsm,order\n")


_ensure_bootstrap_csv()
# argv must be set BEFORE src.lib.config is imported anywhere.
# ``--output-filename`` bypasses the input-filename naming-pattern rule.
sys.argv = [
    "pytest",
    "--csv",
    str(_BOOTSTRAP_CSV),
    "--output-filename",
    "test_out",
]


CSV_HEADER = "point_id,cluster_id,type,lon_x,lat_y,elevation_from_dsm,order\n"


def write_waypoint_csv(path: Path, wpt_rows, cpt_rows) -> Path:
    """Write a harpia waypoints CSV interleaving wpt and cpt rows.

    ``wpt_rows`` / ``cpt_rows`` are lists of
    ``(point_id, lon_x, lat_y, elevation_from_dsm, order)`` tuples. Rows are
    interleaved wpt, cpt, wpt, cpt, ..., wpt (one more wpt than cpt) which is the
    layout BuildCSV produces and the builders expect.
    """
    lines = [CSV_HEADER]
    for i, (pid, lon, lat, elev, order) in enumerate(wpt_rows):
        lines.append(f"{pid},0,wpt,{lon},{lat},{elev},{order}\n")
        if i < len(cpt_rows):
            cpid, clon, clat, celev, corder = cpt_rows[i]
            lines.append(f"{cpid},0,cpt,{clon},{clat},{celev},{corder}\n")
    path.write_text("".join(lines))
    return path


@pytest.fixture
def configured(tmp_path):
    """Point the config singleton at a temp output folder, restore afterwards."""
    from src.lib.config import config

    saved = (config.output_folder, config.output_filename, config.csv_path, config.drone_model)
    config.output_folder = str(tmp_path)
    config.output_filename = "test_out"
    yield config
    (config.output_folder, config.output_filename, config.csv_path, config.drone_model) = saved
