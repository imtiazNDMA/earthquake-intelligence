"""One-time (or after-data-change) build of the element layer indexes.

Usage:
    python scripts/build_cache.py                 # build anything stale
    python scripts/build_cache.py --force         # rebuild everything
    python scripts/build_cache.py roads population
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eqarc.cachebuild import build_all          # noqa: E402  (needs sys.path first)
from eqarc.config import CACHE_DIR, LAYERS      # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build EQ-ARC element caches")
    # No argparse `choices` here: with nargs="*" argparse also validates the
    # empty default against it, which breaks the plain "build everything" call.
    parser.add_argument("layers", nargs="*", metavar="LAYER",
                        help=f"layers to build (default: all). One of: {', '.join(LAYERS)}")
    parser.add_argument("--force", action="store_true",
                        help="rebuild even if the cache looks current")
    args = parser.parse_args(argv)

    unknown = [name for name in args.layers if name not in LAYERS]
    if unknown:
        parser.error(f"unknown layer(s): {', '.join(unknown)}. "
                     f"Choose from: {', '.join(LAYERS)}")

    def progress(message: str) -> None:
        print(message, flush=True)

    started = time.perf_counter()
    print(f"Cache directory: {CACHE_DIR}\n", flush=True)
    results = build_all(args.layers or None, progress=progress, force=args.force)
    elapsed = time.perf_counter() - started

    failed = {k: v for k, v in results.items() if isinstance(v, dict) and "error" in v}
    print(f"\nDone in {elapsed:,.1f}s. "
          f"{len(results) - len(failed)}/{len(results)} layers ready.", flush=True)
    for name, info in failed.items():
        print(f"  FAILED {name}: {info['error']}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
