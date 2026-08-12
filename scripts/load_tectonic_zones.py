"""Load Pakistan tectonic zones from a shapefile into the PostGIS tectonic_zone
table. Idempotent: skips if tectonic_zone already has rows (use --force to
reload). Mirrors scripts/load_boundaries.py."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 — pins PROJ
import fiona  # noqa: E402
import psycopg  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402

from eqmon.db import _database_url, apply_schema  # noqa: E402

SHP = Path(__file__).resolve().parents[1] / "data" / "PAK_Tectoniz_Zones" / "PAK_Tectonic_Zones.shp"
NAME_FIELD = "Name"  # inspected: schema has id/Name/Symbol/Descriptio; Name is human-readable text
SIMPLIFY_DEG = 0.001

INSERT = (
    "INSERT INTO tectonic_zone (name, geom) VALUES (%s, "
    "ST_Multi(ST_SimplifyPreserveTopology("
    "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s)))"
)


def main() -> None:
    p = argparse.ArgumentParser(description="Load tectonic zones into PostGIS")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    if not SHP.exists():
        raise SystemExit(f"Zone shapefile not found: {SHP}")
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        apply_schema(conn)
        existing = conn.execute("SELECT count(*) FROM tectonic_zone").fetchone()[0]
        if existing and not args.force:
            print(f"tectonic_zone already has {existing} rows; skipping (use --force)")
            return
        conn.execute("TRUNCATE tectonic_zone RESTART IDENTITY CASCADE")
        count = 0
        with conn.cursor() as cur, fiona.open(SHP) as src:
            for i, feat in enumerate(src):
                if feat["geometry"] is None:
                    continue
                props = dict(feat["properties"])
                name = str(props.get(NAME_FIELD) or f"Zone {i + 1}")
                geom = json.dumps(mapping(shape(feat["geometry"])))
                cur.execute(INSERT, (name, geom, SIMPLIFY_DEG))
                count += 1
        total = conn.execute("SELECT count(*) FROM tectonic_zone").fetchone()[0]
        print(f"loaded {count} zones; tectonic_zone total rows: {total}")


if __name__ == "__main__":
    main()
