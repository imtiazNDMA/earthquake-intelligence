"""Backfill available USGS and PMD observations into the regional catalog.

USGS is queried from 1900 by default using count-sized windows. PMD is pulled
once because its authorized endpoint returns its full available catalog and has
no documented historical range parameters.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from eqmon import db
from eqmon.events.ingest import INGEST_ADVISORY_LOCK, finalize_ingest, ingest
from eqmon.events.sources import PMDSource, USGSSource


def _utc_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


class _HistoricalUSGS:
    name = "USGS"

    def __init__(self, start: datetime, end: datetime,
                 min_magnitude: float | None):
        self.start = start
        self.end = end
        self.source = USGSSource(
            min_magnitude=min_magnitude, timeout=60.0)

    def fetch(self, since=None, updatedafter=None):
        return self.source.fetch_range(self.start, self.end)

    def fetch_batch(self, since=None, updatedafter=None):
        return self.source.fetch_range_batch(self.start, self.end)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill available regional earthquake observations")
    parser.add_argument("--source", choices=("all", "usgs", "pmd"), default="all")
    parser.add_argument("--start", type=_utc_date,
                        default=_utc_date("1900-01-01"))
    parser.add_argument("--end", type=_utc_date,
                        default=datetime.now(timezone.utc))
    parser.add_argument("--min-magnitude", type=float, default=None,
                        help="Optional USGS floor. Omit to request all magnitudes.")
    args = parser.parse_args()
    if args.end <= args.start:
        parser.error("--end must be after --start")

    db.init_schema()
    results = []
    with db.get_conn() as conn:
        # Block scheduler writes from older API processes that predate the
        # advisory-lock protocol. The lock is released on commit or rollback.
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (INGEST_ADVISORY_LOCK,))
        conn.execute("LOCK TABLE seismic_event IN SHARE ROW EXCLUSIVE MODE")
        if args.source in {"all", "usgs"}:
            print(f"Fetching USGS observations from {args.start.date()} to {args.end.date()}...")
            result = ingest(
                conn,
                _HistoricalUSGS(args.start, args.end, args.min_magnitude),
                postprocess=False,
            )
            results.append(result)
            if result.errors:
                conn.rollback()
                raise RuntimeError("USGS backfill failed: " + "; ".join(result.errors[:5]))

        if args.source in {"all", "pmd"}:
            print("Fetching the full catalog exposed by the authorized PMD endpoint...")
            result = ingest(conn, PMDSource(timeout=60.0), postprocess=False)
            results.append(result)
            if result.errors or result.fetched == 0:
                conn.rollback()
                detail = "; ".join(result.errors[:5]) or "authorized endpoint returned no usable events"
                raise RuntimeError("PMD backfill failed: " + detail)

        print("Resolving cross-source duplicates and tectonic zones...")
        finalize_ingest(conn, classify_sequences=False)
        conn.commit()

        rows = conn.execute(
            "SELECT source, COUNT(*), MIN(occurred_at), MAX(occurred_at) "
            "FROM seismic_event GROUP BY source ORDER BY source"
        ).fetchall()

    for result in results:
        print(
            f"{result.source}: fetched {result.fetched}, inserted {result.inserted}, "
            f"rejected {result.rejected}"
        )
    print("Stored source coverage (not a completeness guarantee):")
    for source, count, earliest, latest in rows:
        print(f"  {source}: {count} records, {earliest} to {latest}")


if __name__ == "__main__":
    main()
