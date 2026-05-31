"""Tests for KMZ packaging.

``CreateKMZ`` (src/lib/create_kmz.py:9) zips
``{output_folder}/{output_filename}/wpmz/{template.kml,waylines.wpml}`` into a
DJI-compatible ``.kmz`` archive with members under the ``wpmz/`` prefix.
"""
import zipfile
from pathlib import Path

from src.lib.create_kmz import CreateKMZ


def _seed_wpmz(output_folder: Path, output_filename: str):
    wpmz = output_folder / output_filename / "wpmz"
    wpmz.mkdir(parents=True, exist_ok=True)
    (wpmz / "template.kml").write_text("<kml>template</kml>")
    (wpmz / "waylines.wpml").write_text("<kml>waylines</kml>")


def test_kmz_contains_expected_wpmz_members(configured, tmp_path):
    configured.debug_mode = False
    _seed_wpmz(tmp_path, "test_out")
    c = CreateKMZ()
    c.create_kmz()

    kmz = tmp_path / "test_out" / "test-out.kmz"  # '_' -> '-' in dji_name
    assert kmz.exists()
    assert zipfile.is_zipfile(kmz)

    with zipfile.ZipFile(kmz) as z:
        assert z.testzip() is None  # no corrupt members
        names = z.namelist()
        assert "wpmz/template.kml" in names
        assert "wpmz/waylines.wpml" in names
        for name in ("wpmz/template.kml", "wpmz/waylines.wpml"):
            assert len(z.read(name)) > 0  # members non-empty


def test_kmz_omits_missing_members(configured, tmp_path):
    # Only template.kml present; waylines.wpml absent -> not added, no crash.
    configured.debug_mode = False
    wpmz = tmp_path / "test_out" / "wpmz"
    wpmz.mkdir(parents=True, exist_ok=True)
    (wpmz / "template.kml").write_text("<kml/>")
    c = CreateKMZ()
    c.create_kmz()
    with zipfile.ZipFile(tmp_path / "test_out" / "test-out.kmz") as z:
        assert z.namelist() == ["wpmz/template.kml"]
