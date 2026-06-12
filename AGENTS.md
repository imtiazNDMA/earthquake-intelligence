# AGENTS.md — eqMonitoring2

## Toolchain (non-negotiable)
- **Package manager:** `uv` — **not** pip, pipenv, or Poetry. The lockfile is `uv.lock`.
  ```bash
  uv sync --group dev          # install everything (dev deps in pyproject.toml [dependency-groups])
  uv run python <file>.py      # run any script with deps activated
  uv run pytest -q             # run tests
  uv run uvicorn eqmon.api:app --port 8000   # start dev server
  ```
- **Python >=3.12** required (`.python-version` enforces it).

## Build pipeline — order matters
One-time data prep, must run in this sequence:

1. `python scripts/rasterize_vs30.py` — produces `data/Vs30.tif` (tens-of-MB GeoTIFF). **Vs30 is never in the database**; kept as COG on disk, loaded by NumPy at runtime.
2. `python scripts/load_boundaries.py` — loads simplified admin polygons (~100 m) into PostGIS. Requires `CREATE EXTENSION postgis` in the target DB first (done outside this repo).
3. `python scripts/build_tiles.py` — bakes boundary layers into `.pmtiles` vector tiles (needs Docker for tippecanoe). Only needed for frontend rendering.

**DB schema** is managed via the migration runner in `db.py`. Migrations live in `migrations/NNN_name.sql` (filename order = apply order). Run `uv run python -c "from eqmon.db import init_schema; init_schema()"` to apply pending migrations. The tracking table `_schema_migrations` records what's been applied.

## Tests
- Pure-logic tests run without any DB connection.
- Integration+DB tests **skip cleanly** when `DATABASE_URL_TEST` is unset — no harm, no error.
- Single package under `src/eqmon/`; all test files under `tests/`. Run targeted: `uv run pytest tests/test_foo.py`.
- pytest config: `pythonpath = ["src"]`, `testpaths = ["tests"]` (from `pyproject.toml`).

## Single-package layout
`src/eqmon/` — one package, no monorepo sub-packages. Key modules:
- `api.py` — FastAPI entrypoint, serves `/intensity` and `/events/*`
- `intensity.py` — vectorized NumPy PGA→MMI formula
- `vs30.py` — loads `data/Vs30.tif` into coordinate-aware grid
- `contours.py` — MMI grid → filled-band GeoJSON
- `db.py` — PostGIS connection pool + `init_schema()`
- `events/` — `sources.py` (USGS + MET stub), `ingest.py` (dedup), `repo.py`

## Important constraints not obvious from filenames
- **Vs30 COG lives on disk, not in DB.** Agents have moved it into PostGIS before — don't.
- **PostGIS extensions must be created manually** (`CREATE EXTENSION postgis` in each database). Not done by any script in this repo.
- **No CI/CD workflows** in this repo (no `.github/`). No codegen, no pre-commit hooks.
- **Dedup rule:** events within 60 s / 50 km cluster; higher-priority source (MET > USGS) wins.
- **Default site condition:** Vs30 = 760 m/s when grid has no value.

## Existing instruction files
- `CLAUDE.md` — architecture overview and dev workflow (stale on dependency install — ignore its `requirements*.txt` references, use `uv sync`).
- `CONTEXT.md` — domain language glossary for the seismic intelligence domain.

## Quick reference
| Task | Command |
|------|---------|
| Install deps | `uv sync --group dev` |
| Run tests | `uv run pytest -q` |
| Run single test file | `uv run pytest tests/test_foo.py` |
| Start dev server | `uv run uvicorn eqmon.api:app --port 8000` |
| Apply DB schema + pending migrations | `uv run python -c "from eqmon.db import init_schema; init_schema()"` |
| Add a new migration | create `migrations/NNN_name.sql` (filename order = apply order) |
| Build Vs30 raster | `uv run python scripts/rasterize_vs30.py` |
| Load admin boundaries | `uv run python scripts/load_boundaries.py` |
| Build vector tiles | `uv run python scripts/build_tiles.py` |
