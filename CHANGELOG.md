# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `photo_heading`, choosing the aircraft yaw for each photo burst. The default
  `north` rotates to true north before shooting, as before, and its output is
  byte-identical; `arrival` keeps the heading the aircraft flew in with, which
  saves a rotation at every feature and the battery time it costs. Worth keeping
  `north` when photos of the same feature are compared through time, since a
  constant yaw makes the frames line up.

  The rotation was commanded by the `orientedShoot` action itself, which
  hardcoded `aircraftHeading` to `0` -- not by the waypoint heading mode, which
  already brought the aircraft in on the leg's own bearing. Each burst heading is
  the bearing of the leg into that feature, and both `aircraftHeading` and
  `gimbalYawRotateAngle` carry it, as DJI requires them to agree on these
  airframes. The first feature is reached from the take-off site, which the
  waypoints CSV does not record, so it faces the way out to the second instead.

## [1.3.0] - 2026-09-05

### Added

- Support for the Matrice 4D (`drone_model: m4d`), with its own mission
  template under `templates/m4d-onewpt-wpmz/`. It flies the same three-shot
  sequence as the M4E and differs only in its drone (`100`), payload (`98`)
  and oriented-camera (`98`) enum values, plus a `payloadLensIndex` that its
  remote controller writes into `template.kml` as well as `waylines.wpml`.

### Changed

- **Breaking.** Command-line short options now follow the POSIX convention of a
  single character after a single dash. The multi-character aliases (`-csv`,
  `-dsm`, `-op`, `-of`, `-aoi`, `-to`, `-proj`, `-ts`, `-alt`) are gone; every
  option keeps its `--long` form, which is what the documented examples use.

  | Option | Was | Now |
  | --- | --- | --- |
  | `--csv` | `-csv` | *(long form only)* |
  | `--dsm` | `-dsm` | `-d` |
  | `--output-path` | `-op` | `-o` |
  | `--output-filename` | `-of` | `-n` |
  | `--aoi` | `-aoi` | `-a` |
  | `--takeoff-coords` | `-to` | `-t` |
  | `--takeoff-coords-projected` | `-proj` | *(long form only)* |
  | `--touch-sky` | `-ts` | `-s` |
  | `--touch-sky-interval` | `-n` | *(long form only)* |
  | `--touch-sky-altitude` | `-alt` | *(long form only)* |
  | `--debug` | `-d` | `-v` |

  Note that `-d` changed hands: it used to mean `--debug` and now means `--dsm`.
  A stale `-d` errors with "expected one argument" rather than misbehaving.

- The global waypoint turn mode (`wpml:globalWaypointTurnMode`) is now
  `coordinateTurn`. The aircraft arcs through the transit and approach
  waypoints instead of stopping at each one, cutting the stop-and-go between
  trees. Two kinds of waypoint still override it with a full stop
  (`toPointAndStopWithDiscontinuityCurvature`): the photo waypoint, so the
  camera fires from a standstill, and the two ends of the wayline. All three
  templates changed.

- `wpml:waypointTurnDampingDist` is now computed per waypoint instead of being
  a single hardcoded radius. An arc radius wider than half the leg it blends
  into is rejected in flight with "Waypoint turning intercept error (1550)",
  and the legs here vary from centimetres to tens of metres: the hop from a
  transit waypoint down to its approach waypoint collapses whenever a
  checkpoint sits at the same elevation as its tree. Each radius is now a third
  of the shorter adjacent leg, reproducing what the remote controller computes
  when a mission is opened and re-saved, so a mission flies straight off the
  transfer.

- The touch-sky apex keeps the full stop. Its two legs double back on each
  other, so it is the one corner an arc would round off entirely, levelling the
  aircraft out short of the altitude the climb exists to reach.

### Fixed

- M4E: the 1x photo of each waypoint is now taken with a `takePhoto` action in
  wide mode instead of `orientedShoot`, which always fires the zoom camera.
  Zoom photos get no DJI Time Sync, so their RTK position was wrong. The tele
  and med shots still use `orientedShoot`; the M3E is unchanged.
- M4E: the `takePhoto` action now matches the remote controller's own export
  byte for byte -- `fileSuffix` first, `payloadLensIndex` (`visable`) last and
  only in `waylines.wpml`, and a centred `focus` action emitted just before it.
- M4E: `orientedShoot` actions in `waylines.wpml` now carry the
  `payloadLensIndex` (`visable`) the remote controller writes; it was missing.
- Transit waypoints in `waylines.wpml` were hardcoded to 15 m/s, contradicting
  the M4E and M4D templates, which declare 21 m/s. The speed now comes from the
  template's own `wpml:autoFlightSpeed`. The approach waypoint keeps its 3 m/s.

## [1.2.0] - 2026-08-26

### Added

- `scripts/select_crowns.py`, a standalone pre-processing tool that shortlists
  candidate tree crowns for close-up missions. Five optional filters (area of
  interest, minimum area, already-visited waypoints, already-known crowns, and
  DSM relief) each run only when their input is supplied, and every step
  reports how many crowns it removed.
- `config/select_crowns_template.yaml` documenting every crown-selection
  setting.
- AOI selection by attribute: `aoi_qualifier` may now be given on its own, in
  which case the AOI feature whose `qualifier` column matches it is selected.
  `aoi_index` remains available to select by 1-based position.
- Format validation for CSV inputs: required columns must be present, the
  coordinate and elevation columns must be numeric, and the file must contain
  at least one `wpt` and one `cpt` row.
- Demo video in the README.

### Changed

- `aoi_qualifier` no longer requires `aoi_index` to be specified.
- Output filenames derived from a CSV input now strip a trailing known
  drone-model suffix before appending the current model, so re-running an
  existing waypoints CSV for another drone no longer stacks suffixes.
- The input-filename naming convention is now enforced only for features-based
  runs; a CSV input is treated as previously generated output.

### Fixed

- Corrected the Zenodo DOI in the README badge.

## [1.1.1] - 2026-08-24

### Added

- First automated test suite covering CSV route planning (TSP), KML/WPML
  generation, and KMZ packaging.
- Continuous integration via GitHub Actions: a ruff lint job
  (`ruff check` + `ruff format --check`) and a pytest job across Python
  3.11-3.13.
- `pre-commit` configuration running ruff and ruff-format.
- `pyproject.toml` with the ruff lint/format configuration
  (select E/F/I/B/UP/SIM/PL, line length 100).
- This changelog.
- `CITATION.cff` and a Zenodo DOI badge in the README.
- Configurable OR-Tools solver time limit for the TSP
  (`tsp_time_limit_seconds`).

### Changed

- Reformatted the codebase with `ruff format` and applied ruff autofixes.
- Migrated the configuration model to Pydantic v2 `ConfigDict`.
- Renamed the `type` parameter to `point_type` in the KML and WPML builders.

### Fixed

- Explicit error when the DSM uses a geographic CRS or does not cover the
  input features.
- Clear error when the waypoint CSV contains no waypoints.
- Timeout added to the EGM96 download request, which could otherwise hang
  indefinitely.
- Typos in an error message, and broken badge links in the README.

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

[Unreleased]: https://github.com/traitlab/harpia/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/traitlab/harpia/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/traitlab/harpia/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/traitlab/harpia/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/traitlab/harpia/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/traitlab/harpia/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/traitlab/harpia/releases/tag/v1.0.0
