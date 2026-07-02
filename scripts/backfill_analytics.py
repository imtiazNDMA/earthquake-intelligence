# scripts/backfill_analytics.py
"""One-off: populate is_mainshock/sequence_id/zone_id over the existing catalog
(run once after deploying the analytics migration + tectonic-zone load)."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401
import psycopg  # noqa: E402

from eqmon.db import _database_url, apply_schema  # noqa: E402
from eqmon.events.ingest import _decluster, _assign_zones  # noqa: E402


def main() -> None:
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        apply_schema(conn)
        _decluster(conn)
        _assign_zones(conn)
        mains = conn.execute(
            "SELECT count(*) FROM seismic_event WHERE is_mainshock = TRUE"
        ).fetchone()[0]
        zoned = conn.execute(
            "SELECT count(*) FROM seismic_event WHERE zone_id IS NOT NULL"
        ).fetchone()[0]
        print(f"backfill done: {mains} mainshocks, {zoned} events zoned")


if __name__ == "__main__":
    main()
