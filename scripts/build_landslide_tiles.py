"""Package categorical landslide COGs as transparent raster PMTiles.

Run prepare_landslide_data.py first. This script creates a temporary RGBA view
of each categorical COG and delegates tile packing to the pinned rio-pmtiles
Rasterio plugin.

Usage:
  uv run python scripts/build_landslide_tiles.py
  uv run python scripts/build_landslide_tiles.py --regions AJK GB --force
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 - pins PROJ
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.warp import transform_bounds  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "landslides"
OUTPUT_DIR = ROOT / "web" / "landslides"
CLASS_VALUE = 5
NODATA = 255
COLOR = "#D73027"
RGB = tuple(int(COLOR[i:i + 2], 16) for i in (1, 3, 5))
REGIONS = {
    "AJK": ("Azad Jammu and Kashmir", "ajk", 13),
    "GB": ("Gilgit-Baltistan", "gb", 13),
    "KP": ("Khyber Pakhtunkhwa", "kp", 14),
    "Baloch": ("Balochistan", "baloch", 12),
}


def _rgba_source(source: Path, target: Path) -> None:
    with rasterio.open(source) as src:
        profile = src.profile.copy()
        profile.update(count=4, nodata=None, photometric="RGB", compress="DEFLATE",
                       BIGTIFF="IF_SAFER")
        with rasterio.open(target, "w", **profile) as dst:
            for _, window in src.block_windows(1):
                values = src.read(1, window=window)
                selected = values == CLASS_VALUE
                rgba = np.zeros((4, values.shape[0], values.shape[1]), dtype="uint8")
                for band, channel in enumerate(RGB):
                    rgba[band, selected] = channel
                rgba[3, selected] = 255
                dst.write(rgba, window=window)


def build_region(key: str, *, force: bool = False, workers: int = 4) -> dict:
    label, stem, max_zoom = REGIONS[key]
    source = SOURCE_DIR / f"{stem}.tif"
    output = OUTPUT_DIR / f"{stem}.pmtiles"
    temporary = SOURCE_DIR / f".{stem}.rgba.tif"
    if not source.exists():
        raise FileNotFoundError(f"Prepared COG not found: {source}")
    if output.exists() and not force:
        with rasterio.open(source) as src:
            bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        return _entry(key, label, stem, max_zoom, bounds, output)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    temporary.unlink(missing_ok=True)
    _rgba_source(source, temporary)
    rio = shutil.which("rio")
    if rio is None:
        raise RuntimeError("Rasterio CLI not found; run through `uv run python`")
    command = [
        rio, "pmtiles", str(temporary), str(output),
        "--format", "PNG", "--rgba", "--resampling", "nearest",
        "--zoom-levels", f"4..{max_zoom}", "--exclude-empty-tiles",
        "-j", str(workers), "--name", f"{label} landslide susceptibility",
        "--description", "Filtered Very High landslide susceptibility mask",
    ]
    try:
        subprocess.run(command, check=True)
    finally:
        temporary.unlink(missing_ok=True)
    with rasterio.open(source) as src:
        bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
    print(f"  {output.relative_to(ROOT)}: {output.stat().st_size / 1024 / 1024:.1f} MB")
    return _entry(key, label, stem, max_zoom, bounds, output)


def _entry(key: str, label: str, stem: str, max_zoom: int, bounds, output: Path) -> dict:
    return {
        "key": key,
        "label": label,
        "url": f"landslides/{stem}.pmtiles",
        "bounds": [round(value, 6) for value in bounds],
        "min_zoom": 4,
        "max_zoom": max_zoom,
        "bytes": output.stat().st_size,
    }


def existing_region_entry(key: str) -> dict | None:
    """Describe an already-built archive so partial builds do not hide it."""
    label, stem, max_zoom = REGIONS[key]
    source = SOURCE_DIR / f"{stem}.tif"
    output = OUTPUT_DIR / f"{stem}.pmtiles"
    if not source.exists() or not output.exists():
        return None
    with rasterio.open(source) as src:
        bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
    return _entry(key, label, stem, max_zoom, bounds, output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=REGIONS, default=list(REGIONS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    built = {key: build_region(key, force=args.force, workers=args.workers)
             for key in args.regions}
    entries = [built.get(key) or existing_region_entry(key) for key in REGIONS]
    entries = [entry for entry in entries if entry is not None]
    manifest = {
        "dataset_id": "landslide_susceptibility",
        "generated_at": datetime.now(UTC).isoformat(),
        "title": "Very High landslide susceptibility",
        "description": "Filtered Very High class only; transparent areas may be unassessed.",
        "class": {"value": CLASS_VALUE, "label": "Very High", "color": COLOR},
        "default_opacity": 0.62,
        "regions": entries,
    }
    path = OUTPUT_DIR / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
