# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- First automated test suite covering CSV route planning (TSP), KML/WPML
  generation, and KMZ packaging.
- Continuous integration via GitHub Actions: a ruff lint job
  (`ruff check` + `ruff format --check`) and a pytest job across Python
  3.11-3.13.
- `pre-commit` configuration running ruff and ruff-format.
- `pyproject.toml` with the ruff lint/format configuration
  (select E/F/I/B/UP/SIM/PL, line length 100).

### Changed

- Reformatted the codebase with `ruff format` and applied ruff autofixes.

## [1.1.0] - 2026-01-16

### Added

- Compatibility with the DJI Matrice 4E drone.
- Sensor name appended to the output filename.
- Focal length used as the photo-action filename suffix (replacing `zoom`).
- Support for two-digit version numbers in input filenames.

## [1.0.1] - 2025-11-26

### Added

- Explicit error for input files with zero or one feature.
- bioRxiv link in the README.

### Changed

- Input coordinates ordered as `lat lon` to follow ISO 6709.
- Projected coordinates keep their X/Y order as provided.
- Default DSM template configuration references an online asset.

## [1.0.0] - 2025-08-08

### Added

- Initial release: generate optimized DJI drone photo missions from feature
  locations (tree crowns) and a Digital Surface Model. Solves a TSP route,
  builds path checkpoints above obstacles, and exports a DJI-compatible KMZ
  mission package (template KML + waylines WPML). Includes the touch-sky
  feature, optional takeoff-site coordinates, and AOI filtering.

[Unreleased]: https://github.com/traitlab/harpia/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/traitlab/harpia/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/traitlab/harpia/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/traitlab/harpia/releases/tag/v1.0.0
