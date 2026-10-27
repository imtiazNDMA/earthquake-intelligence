"""Download prebuilt layer caches into data/cache/ from a base URL.

For hosts that do not have the 2.3 GB source GeoJSON to run build_cache.py
against. The URL must serve <name>.npz for every layer in LAYERS.

Usage:
  python scripts/fetch_cache.py https://<bucket-url>/arc-cache"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eqarc.config import CACHE_DIR, LAYERS, cache_path  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    base_url = sys.argv[1].rstrip("/")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for name in LAYERS:
        print(f"fetching {name}.npz", flush=True)
        urllib.request.urlretrieve(f"{base_url}/{name}.npz", cache_path(name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
