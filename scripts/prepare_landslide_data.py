"""Reconstruct categorical landslide COGs from filtered polygon masks.

The supplied shapefiles are RasterToPolygon exports containing only gridcode 5
(Very High). This script restores that categorical mask on the measured source
grid. Pixels outside supplied polygons remain 255 (unassessed/nodata); they are
not assigned to a lower susceptibility class.

Usage:
  uv run python scripts/prepare_landslide_data.py
  uv run python scripts/prepare_landslide_data.py --regions AJK GB --force
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 - pins PROJ before geospatial imports
import fiona  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.features import bounds as geometry_bounds  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.shutil import copy as rio_copy  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402
from rasterio.windows import Window, from_bounds  # noqa: E402
from shapely import is_valid, make_valid  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "LS Susceptability Maps"
OUTPUT_DIR = ROOT / "data" / "landslides"
CLASS_VALUE = 5
NODATA = 255
BLOCK_SIZE = 512
CHUNK_SIZE = 2_000
SOURCE_PARTS = (".shp", ".shx", ".dbf", ".prj", ".cpg", ".shp.xml")


@dataclass(frozen=True)
class Region:
    key: str
    label: str
    stem: str
    epsg: int
    pixel_size_m: float


REGIONS = {
    "AJK": Region("AJK", "Azad Jammu and Kashmir", "AJK", 32643, 12.5),
    "GB": Region("GB", "Gilgit-Baltistan", "GB", 32643, 12.5),
    "KP": Region("KP", "Khyber Pakhtunkhwa", "KP", 32642, 10.0),
    "Baloch": Region("Baloch", "Balochistan", "Baloch", 32642, 30.0),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _polygonal_geometry(raw: dict) -> tuple[dict | None, bool]:
    """Return a rasterizable polygon, repairing invalid topology if needed."""
    geom = shape(raw)
    repaired = False
    if not is_valid(geom):
        geom = make_valid(geom)
        repaired = True
    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        parts = [part for part in getattr(geom, "geoms", ())
                 if part.geom_type in {"Polygon", "MultiPolygon"}]
        if not parts:
            return None, repaired
        geom = unary_union(parts)
    return mapping(geom), repaired


def _window_for_shapes(shapes: list[dict], transform, width: int, height: int) -> Window:
    boxes = [geometry_bounds(item) for item in shapes]
    left = min(box[0] for box in boxes)
    bottom = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    top = max(box[3] for box in boxes)
    raw = from_bounds(left, bottom, right, top, transform)
    col_off = max(0, math.floor(raw.col_off))
    row_off = max(0, math.floor(raw.row_off))
    col_end = min(width, math.ceil(raw.col_off + raw.width))
    row_end = min(height, math.ceil(raw.row_off + raw.height))
    return Window(col_off, row_off, max(1, col_end - col_off), max(1, row_end - row_off))


def _burn_chunk(dst, geometries: list[dict]) -> None:
    window = _window_for_shapes(geometries, dst.transform, dst.width, dst.height)
    current = dst.read(1, window=window)
    burned = rasterize(
        ((geom, CLASS_VALUE) for geom in geometries),
        out_shape=current.shape,
        transform=dst.window_transform(window),
        fill=0,
        dtype="uint8",
        all_touched=False,
    )
    current[burned == CLASS_VALUE] = CLASS_VALUE
    dst.write(current, 1, window=window)


def _initialize_nodata(dst) -> None:
    block = np.full((BLOCK_SIZE, BLOCK_SIZE), NODATA, dtype="uint8")
    for _, window in dst.block_windows(1):
        dst.write(block[: int(window.height), : int(window.width)], 1, window=window)


def build_region(region: Region, source_dir: Path, output_dir: Path, *, force: bool = False) -> dict:
    source = source_dir / f"{region.stem}.shp"
    target = output_dir / f"{region.key.lower()}.tif"
    if not source.exists():
        raise FileNotFoundError(f"Landslide source not found: {source}")
    if target.exists() and not force:
        with rasterio.open(target) as existing:
            return {
                "key": region.key,
                "label": region.label,
                "cog": target.name,
                "feature_count": int(existing.tags().get("feature_count", 0)),
                "repaired_count": int(existing.tags().get("repaired_count", 0)),
                "skipped_count": int(existing.tags().get("skipped_count", 0)),
                "source_crs": existing.crs.to_string(),
                "pixel_size_m": region.pixel_size_m,
                "width": existing.width,
                "height": existing.height,
                "bounds": list(existing.bounds),
            }

    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = output_dir / f".{region.key.lower()}.working.tif"
    temporary.unlink(missing_ok=True)
    target.unlink(missing_ok=True)

    with fiona.open(source) as src:
        source_epsg = src.crs.to_epsg()
        if source_epsg != region.epsg:
            raise ValueError(f"{source.name}: expected EPSG:{region.epsg}, got {src.crs}")
        left, bottom, right, top = src.bounds
        width = math.ceil((right - left) / region.pixel_size_m)
        height = math.ceil((top - bottom) / region.pixel_size_m)
        transform = from_origin(left, top, region.pixel_size_m, region.pixel_size_m)
        profile = {
            "driver": "GTiff",
            "width": width,
            "height": height,
            "count": 1,
            "dtype": "uint8",
            "crs": src.crs,
            "transform": transform,
            "nodata": NODATA,
            "tiled": True,
            "blockxsize": BLOCK_SIZE,
            "blockysize": BLOCK_SIZE,
            "compress": "DEFLATE",
            "predictor": 1,
            "BIGTIFF": "IF_SAFER",
        }
        feature_count = repaired_count = skipped_count = 0
        chunk: list[dict] = []
        with rasterio.open(temporary, "w+", **profile) as dst:
            _initialize_nodata(dst)
            for feature in src:
                feature_count += 1
                if feature["properties"].get("gridcode") != CLASS_VALUE:
                    raise ValueError(
                        f"{source.name}: feature {feature_count} has gridcode "
                        f"{feature['properties'].get('gridcode')!r}, expected {CLASS_VALUE}"
                    )
                geom, repaired = _polygonal_geometry(feature["geometry"])
                repaired_count += int(repaired)
                if geom is None:
                    skipped_count += 1
                    continue
                chunk.append(geom)
                if len(chunk) >= CHUNK_SIZE:
                    _burn_chunk(dst, chunk)
                    chunk.clear()
                if feature_count % 100_000 == 0:
                    print(f"  {region.key}: {feature_count:,}/{len(src):,} features")
            if chunk:
                _burn_chunk(dst, chunk)
            dst.update_tags(
                dataset_id="landslide_susceptibility",
                class_value=CLASS_VALUE,
                class_label="Very High",
                feature_count=feature_count,
                repaired_count=repaired_count,
                skipped_count=skipped_count,
                source_file=source.name,
            )

    rio_copy(
        temporary,
        target,
        driver="COG",
        compress="DEFLATE",
        blocksize=BLOCK_SIZE,
        overview_resampling="NEAREST",
        BIGTIFF="IF_SAFER",
    )
    temporary.unlink(missing_ok=True)
    display_path = target.relative_to(ROOT) if target.is_relative_to(ROOT) else target
    print(f"  {display_path}: {feature_count:,} features, "
          f"{repaired_count:,} repaired, {skipped_count:,} skipped")
    return {
        "key": region.key,
        "label": region.label,
        "cog": target.name,
        "feature_count": feature_count,
        "repaired_count": repaired_count,
        "skipped_count": skipped_count,
        "source_crs": f"EPSG:{region.epsg}",
        "pixel_size_m": region.pixel_size_m,
        "width": width,
        "height": height,
        "bounds": [left, bottom, right, top],
    }


def source_inventory(source_dir: Path, regions: Iterable[Region]) -> list[dict]:
    inventory = []
    for region in regions:
        files = []
        for suffix in SOURCE_PARTS:
            path = source_dir / f"{region.stem}{suffix}"
            if path.exists():
                files.append({
                    "name": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                })
        required = {f"{region.stem}{suffix}" for suffix in (".shp", ".shx", ".dbf", ".prj")}
        found = {item["name"] for item in files}
        if missing := required - found:
            raise FileNotFoundError(f"{region.key}: missing source files: {sorted(missing)}")
        inventory.append({"key": region.key, "label": region.label, "files": files})
    return inventory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=REGIONS, default=list(REGIONS))
    parser.add_argument("--force", action="store_true", help="replace existing COGs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = [REGIONS[key] for key in args.regions]
    inventory = source_inventory(SOURCE_DIR, selected)
    products = [build_region(region, SOURCE_DIR, OUTPUT_DIR, force=args.force)
                for region in selected]
    manifest = {
        "dataset_id": "landslide_susceptibility",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_semantics": "Filtered Very High susceptibility polygons only",
        "class": {"value": CLASS_VALUE, "label": "Very High", "color": "#D73027"},
        "nodata": {"value": NODATA, "meaning": "unassessed or outside supplied mask"},
        "regions": inventory,
        "products": products,
    }
    path = OUTPUT_DIR / "source_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
