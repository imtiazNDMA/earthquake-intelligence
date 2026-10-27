"""Build compact binary indexes from the element GeoJSON layers.

Parsing the source layers on every request is not viable - population.geojson
alone is 1.77 GB / 1.33 M features. This module reads each layer once and
writes a small ``.npz`` beside it:

  point layers  ->  x, y                        (float64)
  population    ->  x, y, pop_f, pop_m          (age/sex columns pre-summed)
  roads         ->  packed WKB + offsets + bbox (float64)

Pre-summing the 36 ``glob_[fm]_*`` columns at build time is what makes the
population query O(points) instead of O(points x 36) per request.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
from osgeo import ogr

from .config import AGE_BANDS, CACHE_DIR, LAYERS, cache_path, layer_path

ogr.UseExceptions()

CACHE_VERSION = 1
Progress = Callable[[str], None]


def _log(progress: Progress | None, message: str) -> None:
    if progress:
        progress(message)


def _open_layer(path: Path):
    ds = ogr.Open(str(path), 0)
    if ds is None:
        raise ValueError(f"Could not open {path}")
    return ds, ds.GetLayer(0)


def _point_xy(geom: ogr.Geometry) -> tuple[float, float] | None:
    """Extract a representative lon/lat from a point-ish geometry."""
    if geom is None:
        return None
    flat = ogr.GT_Flatten(geom.GetGeometryType())
    if flat == ogr.wkbPoint:
        return geom.GetX(0), geom.GetY(0)
    try:                                  # MultiPoint / anything else
        centroid = geom.Centroid()
        return centroid.GetX(0), centroid.GetY(0)
    except Exception:
        return None


def _resolve_pop_fields(defn: ogr.FeatureDefn) -> tuple[list[int], list[int], list[str]]:
    """Map the glob_f_* / glob_m_* age columns to field indexes."""
    available = {defn.GetFieldDefn(i).GetName(): i for i in range(defn.GetFieldCount())}
    f_idx, m_idx, used = [], [], []
    for age in AGE_BANDS:
        fname, mname = f"glob_f_{age}", f"glob_m_{age}"
        if fname in available and mname in available:
            f_idx.append(available[fname])
            m_idx.append(available[mname])
            used.append(str(age))
    if not f_idx:
        raise ValueError(
            "population layer has no glob_f_*/glob_m_* column pairs; "
            f"found fields: {sorted(available)[:15]}"
        )
    return f_idx, m_idx, used


# --------------------------------------------------------------------------
# per-kind builders
# --------------------------------------------------------------------------

def _build_point_layer(name: str, src: Path, progress: Progress | None) -> dict[str, Any]:
    ds, layer = _open_layer(src)
    total = layer.GetFeatureCount()
    xs = np.empty(total, dtype=np.float64)
    ys = np.empty(total, dtype=np.float64)

    n = 0
    for i, feature in enumerate(layer):
        xy = _point_xy(feature.GetGeometryRef())
        if xy is None:
            continue
        xs[n], ys[n] = xy
        n += 1
        if progress and i and i % 50_000 == 0:
            _log(progress, f"  {name}: {i:,}/{total:,}")

    ds = None
    meta = {"kind": "point", "count": int(n), "version": CACHE_VERSION}
    np.savez(cache_path(name), x=xs[:n], y=ys[:n], meta=np.array(repr(meta)))
    return meta


def _build_population(name: str, src: Path, progress: Progress | None) -> dict[str, Any]:
    ds, layer = _open_layer(src)
    defn = layer.GetLayerDefn()
    f_idx, m_idx, used_ages = _resolve_pop_fields(defn)
    total = layer.GetFeatureCount()

    xs = np.empty(total, dtype=np.float64)
    ys = np.empty(total, dtype=np.float64)
    pf = np.empty(total, dtype=np.float32)
    pm = np.empty(total, dtype=np.float32)

    n = 0
    for i, feature in enumerate(layer):
        xy = _point_xy(feature.GetGeometryRef())
        if xy is None:
            continue
        female = 0.0
        for idx in f_idx:
            if feature.IsFieldSetAndNotNull(idx):
                female += feature.GetFieldAsDouble(idx)
        male = 0.0
        for idx in m_idx:
            if feature.IsFieldSetAndNotNull(idx):
                male += feature.GetFieldAsDouble(idx)
        xs[n], ys[n], pf[n], pm[n] = xy[0], xy[1], female, male
        n += 1
        if progress and i and i % 50_000 == 0:
            _log(progress, f"  {name}: {i:,}/{total:,}")

    ds = None
    meta = {
        "kind": "pop",
        "count": int(n),
        "age_bands": used_ages,
        "female_total": float(pf[:n].sum(dtype=np.float64)),
        "male_total": float(pm[:n].sum(dtype=np.float64)),
        "version": CACHE_VERSION,
    }
    np.savez(cache_path(name), x=xs[:n], y=ys[:n],
             pop_f=pf[:n], pop_m=pm[:n], meta=np.array(repr(meta)))
    return meta


def _build_line_layer(name: str, src: Path, progress: Progress | None) -> dict[str, Any]:
    """Store lines as packed WKB plus a bbox table for cheap prefiltering."""
    ds, layer = _open_layer(src)
    total = layer.GetFeatureCount()

    blobs: list[bytes] = []
    bboxes = np.empty((total, 4), dtype=np.float64)

    n = 0
    for i, feature in enumerate(layer):
        geom = feature.GetGeometryRef()
        if geom is None or geom.IsEmpty():
            continue
        try:
            wkb = bytes(geom.ExportToWkb())
        except Exception:
            continue
        minx, maxx, miny, maxy = geom.GetEnvelope()
        blobs.append(wkb)
        bboxes[n] = (minx, miny, maxx, maxy)
        n += 1
        if progress and i and i % 50_000 == 0:
            _log(progress, f"  {name}: {i:,}/{total:,}")

    ds = None
    lengths = np.fromiter((len(b) for b in blobs), dtype=np.int64, count=n)
    offsets = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(lengths, out=offsets[1:])
    packed = np.frombuffer(b"".join(blobs), dtype=np.uint8)

    meta = {"kind": "line", "count": int(n),
            "wkb_bytes": int(packed.nbytes), "version": CACHE_VERSION}
    np.savez(cache_path(name), wkb=packed, offsets=offsets,
             bbox=bboxes[:n], meta=np.array(repr(meta)))
    return meta


BUILDERS = {
    "point": _build_point_layer,
    "pop": _build_population,
    "line": _build_line_layer,
}


def build_layer(name: str, progress: Progress | None = None,
                force: bool = False) -> dict[str, Any]:
    """Build (or reuse) the cache for a single element layer."""
    spec = LAYERS.get(name)
    if spec is None:
        raise ValueError(f"Unknown layer: {name}")

    src = layer_path(name)
    if not src.exists():
        raise FileNotFoundError(f"Missing source layer: {src}")

    dest = cache_path(name)
    if dest.exists() and not force and dest.stat().st_mtime >= src.stat().st_mtime:
        _log(progress, f"{name}: cache up to date, skipping")
        return {"kind": spec["kind"], "skipped": True}

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    size_mb = src.stat().st_size / 1e6
    _log(progress, f"{name}: reading {size_mb:,.0f} MB ...")

    started = time.perf_counter()
    meta = BUILDERS[spec["kind"]](name, src, progress)
    elapsed = time.perf_counter() - started

    meta["seconds"] = round(elapsed, 1)
    meta["cache_mb"] = round(dest.stat().st_size / 1e6, 1)
    _log(progress,
         f"{name}: {meta.get('count', 0):,} features -> "
         f"{meta['cache_mb']} MB in {elapsed:,.1f}s")
    return meta


def build_all(names: list[str] | None = None, progress: Progress | None = None,
              force: bool = False) -> dict[str, Any]:
    targets = names or list(LAYERS)
    results: dict[str, Any] = {}
    for name in targets:
        try:
            results[name] = build_layer(name, progress=progress, force=force)
        except Exception as exc:                      # keep going; report at the end
            _log(progress, f"{name}: FAILED - {exc}")
            results[name] = {"error": str(exc)}
    return results
