"""Build vector tiles (.pmtiles) for the map overlays.

Runs tippecanoe inside Docker (no native Windows build needed) and writes one
archive per layer into web/tiles/. Admin layers tile directly from pre-built
GeoJSON; faults and plates are first converted shp->GeoJSON (forced 2D) into a
temp dir. Each archive's internal tile layer is named with ``-l <id>`` so the
frontend can reference it.

Idempotent: skips layers whose .pmtiles already exist. Use ``--force`` to
rebuild all. Tiles are gitignored derived artifacts.

Prerequisites:
  - Docker Desktop (running) — tested with indigoag/tippecanoe image

Usage:
  uv run python scripts/build_tiles.py          # build missing tiles
  uv run python scripts/build_tiles.py --force   # rebuild all"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 — pins PROJ
import fiona  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402
from shapely import force_2d  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TILES = ROOT / "web" / "tiles"
TMP = DATA / "_tiles_src"          # gitignored temp GeoJSON for shp-only layers
DOCKER_IMAGE = "indigoag/tippecanoe"  # felt/tippecanoe upstream; v2.23.0 with pmtiles support

# id, source path (relative to ROOT), extra tippecanoe args
ADMIN_LAYERS = [
    ("national",  "data/Boundaries_Data/Pakistan_National.geojson",  ["-z8"]),
    ("provinces", "data/Boundaries_Data/Pakistan_Provinces.geojson", ["-z9"]),
    ("districts", "data/Boundaries_Data/Pakistan_Districts.geojson", ["-z11", "--drop-densest-as-needed"]),
    ("tehsils",   "data/Boundaries_Data/Pakistan_Tehsils.geojson",   ["-z12", "--drop-densest-as-needed"]),
]
# id, source shapefile (relative to ROOT), extra args — converted to GeoJSON first
SHP_LAYERS = [
    ("faults",           "data/Global_Active_Earthquake_Faults-shp/Global_Active_Earthquake_Faults.shp", ["-z10", "--drop-densest-as-needed"]),
    ("plate_boundaries", "data/Tectonic Plate Boundaries/Tectonic_Plate_Boundaries.shp",                  ["-z8"]),
    ("plates",           "data/Tectonic Plates/Tectonic_Plates.shp",                                      ["-z6"]),
]


# On Windows/Git-Bash, the MSYS path translator rewrites /data → C:/Program Files/Git/data.
# Setting MSYS_NO_PATHCONV=1 disables that translation for all docker subprocess calls.
_DOCKER_ENV = {**os.environ, "MSYS_NO_PATHCONV": "1"}


def _require_docker() -> None:
    try:
        subprocess.run(["docker", "--version"], check=True,
                       capture_output=True, text=True, env=_DOCKER_ENV)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise SystemExit("Docker is required to build tiles (start Docker Desktop). "
                         f"docker --version failed: {e}")


def _check_source(path_rel: str) -> None:
    full = ROOT / path_rel
    if not full.exists():
        raise SystemExit(
            f"Source not found: {full}\n"
            "Obtain the required boundary/geological data and place it at the "
            "expected path.")


def _shp_to_geojson(shp_rel: str, layer_id: str) -> str:
    """Convert a shapefile to a 2D GeoJSON FeatureCollection under TMP.
    Returns the new path relative to ROOT (for the Docker mount)."""
    out = TMP / f"{layer_id}.geojson"
    feats = []
    with fiona.open(ROOT / shp_rel) as src:
        for f in src:
            if f["geometry"] is None:
                continue  # skip null-geometry records (e.g. placeholder rows)
            geom = mapping(force_2d(shape(f["geometry"])))
            feats.append({"type": "Feature", "properties": dict(f["properties"]),
                          "geometry": geom})
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return str(out.relative_to(ROOT)).replace("\\", "/")


def _needs_rebuild(layer_id: str, force: bool) -> bool:
    if force:
        return True
    out = TILES / f"{layer_id}.pmtiles"
    if out.exists():
        print(f"  {layer_id}.pmtiles exists; skipping (use --force to rebuild)")
        return False
    return True


def _tippecanoe(layer_id: str, src_rel: str, extra: list[str]) -> None:
    """Run tippecanoe in Docker. Paths are relative to ROOT, mounted at /data."""
    out_rel = f"web/tiles/{layer_id}.pmtiles"
    cmd = [
        "docker", "run", "--rm", "-v", f"{ROOT.as_posix()}:/data", DOCKER_IMAGE,
        "tippecanoe", "-o", f"/data/{out_rel}", "-l", layer_id, "-f",
        *extra, f"/data/{src_rel}",
    ]
    print("›", " ".join(cmd))
    subprocess.run(cmd, check=True, env=_DOCKER_ENV)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build .pmtiles vector tiles for map overlays (requires Docker)")
    parser.add_argument("--force", action="store_true",
                        help="Rebuild all tiles even if they already exist")
    parser.add_argument("--docker-image", default=DOCKER_IMAGE,
                        help=f"Tippecanoe Docker image (default: {DOCKER_IMAGE})")
    args = parser.parse_args()

    image = args.docker_image
    _require_docker()
    TILES.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)

    for layer_id, src_rel, extra in ADMIN_LAYERS:
        _check_source(src_rel)
        if _needs_rebuild(layer_id, args.force):
            _tippecanoe(layer_id, src_rel, extra)
    for layer_id, shp_rel, extra in SHP_LAYERS:
        _check_source(shp_rel)
        if _needs_rebuild(layer_id, args.force):
            gj_rel = _shp_to_geojson(shp_rel, layer_id)
            _tippecanoe(layer_id, gj_rel, extra)

    built = sorted(p.name for p in TILES.glob("*.pmtiles"))
    print(f"built {len(built)} tile archives: {built}")
    assert len(built) == 7, "expected 7 .pmtiles archives"


if __name__ == "__main__":
    main()
