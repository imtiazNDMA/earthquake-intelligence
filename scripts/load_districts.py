"""One-time: load boundary/district.geojson into the PostGIS `district` table.

Usage: uv run python scripts/load_districts.py
Requires DATABASE_URL and an applied schema (run eqmon.db.init_schema first, or
this script applies it)."""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 — PROJ pin (harmless here)
import psycopg  # noqa: E402
from eqmon.db import _database_url, apply_schema  # noqa: E402

GEOJSON = Path(__file__).resolve().parents[1] / "boundary" / "district.geojson"


def main() -> None:
    data = json.loads(GEOJSON.read_text(encoding="utf-8"))
    feats = data["features"]
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        apply_schema(conn)
        conn.execute("TRUNCATE district RESTART IDENTITY")
        with conn.cursor() as cur:
            for f in feats:
                props = f["properties"]
                name = props.get("DISTRICT")
                province = props.get("PROVINCE")
                geom = json.dumps(f["geometry"])
                cur.execute(
                    "INSERT INTO district (name, province, geom) "
                    "VALUES (%s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))",
                    (name, province, geom),
                )
        count = conn.execute("SELECT count(*) FROM district").fetchone()[0]
        print(f"loaded {count} districts (geojson had {len(feats)} features)")
        assert count == len(feats), "row count mismatch"


if __name__ == "__main__":
    main()
