"""One-time: load Pakistan admin boundaries (national/province/district/tehsil)
from shapefiles into the PostGIS admin_boundary table.

Geometry is simplified with ST_SimplifyPreserveTopology (~0.001 deg ~= 100 m) on
insert so the impact spatial join stays fast. Full-resolution *display* geometry
is produced separately as vector tiles by scripts/build_tiles.py.

Usage: uv run python scripts/load_boundaries.py
Requires DATABASE_URL and applies the schema itself."""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 — import side effect: pins PROJ
import fiona  # noqa: E402
import psycopg  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402

from eqmon.boundaries import map_feature  # noqa: E402
from eqmon.db import _database_url, apply_schema  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "Boundaries_Data"
SOURCES = {
    "national": DATA / "pak_national.shp",
    "province": DATA / "pak_provinces.shp",
    "district": DATA / "pak_districts.shp",
    "tehsil":   DATA / "pak_tehsils.shp",
}
EXPECTED = {"national": 4, "province": 8, "district": 167, "tehsil": 578}
SIMPLIFY_DEG = 0.001  # ~100 m; coarse vs km-scale MMI bands, keeps joins fast

INSERT = (
    "INSERT INTO admin_boundary (level, name, parent, division, population, geom) "
    "VALUES (%s, %s, %s, %s, %s, "
    "ST_Multi(ST_SimplifyPreserveTopology("
    "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s)))"
)


def main() -> None:
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        apply_schema(conn)
        conn.execute("TRUNCATE admin_boundary RESTART IDENTITY")
        with conn.cursor() as cur:
            for level, path in SOURCES.items():
                count = 0
                with fiona.open(path) as src:
                    for feat in src:
                        cols = map_feature(level, dict(feat["properties"]))
                        geom = json.dumps(mapping(shape(feat["geometry"])))
                        cur.execute(INSERT, (cols["level"], cols["name"], cols["parent"],
                                             cols["division"], cols["population"],
                                             geom, SIMPLIFY_DEG))
                        count += 1
                assert count == EXPECTED[level], \
                    f"{level}: loaded {count}, expected {EXPECTED[level]}"
                print(f"loaded {count} {level}")
        total = conn.execute("SELECT count(*) FROM admin_boundary").fetchone()[0]
        print(f"admin_boundary total rows: {total}")
        assert total == sum(EXPECTED.values()), "total row count mismatch"


if __name__ == "__main__":
    main()
