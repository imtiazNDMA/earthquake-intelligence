"""Count the elements sitting under each dissolved MMI band.

Counting rule
-------------
Bands are processed strongest-shaking-first and every element is claimed by the
*highest* MMI band it falls in, then removed from the pool. That gives three
properties for free:

  * nothing is double-counted where bands touch along their shared contour,
  * nothing is lost on a shared boundary (unlike a strict contains() test),
  * a road spanning several bands is attributed to its worst-case shaking,
    which is the convention response planning expects.

Because the per-band numbers are therefore mutually exclusive, the cumulative
"MMI >= X" view is just a running total from the strongest band down.
"""

from __future__ import annotations

import ast
import threading
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from .config import LAYER_ORDER, LAYERS, cache_path
from .dissolve import Band

# Lines are rebuilt from WKB in slices so a band covering half the country does
# not materialise 600k geometries at once.
LINE_CHUNK = 100_000


class MissingCacheError(RuntimeError):
    """Raised when a layer's cache has not been built yet."""


# --------------------------------------------------------------------------
# cache store
# --------------------------------------------------------------------------

class LayerStore:
    """Lazily loads and holds the cached layer arrays for the process."""

    def __init__(self) -> None:
        self._layers: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        out = {}
        for name in LAYERS:
            path = cache_path(name)
            out[name] = {
                "kind": LAYERS[name]["kind"],
                "label": LAYERS[name]["label"],
                "cached": path.exists(),
                "cache_mb": round(path.stat().st_size / 1e6, 1) if path.exists() else None,
                "loaded": name in self._layers,
            }
        return out

    def missing(self) -> list[str]:
        return [n for n in LAYERS if not cache_path(n).exists()]

    def get(self, name: str) -> dict[str, Any]:
        with self._lock:
            if name in self._layers:
                return self._layers[name]

            path = cache_path(name)
            if not path.exists():
                raise MissingCacheError(
                    f"No cache for '{name}'. Run: python scripts/build_cache.py"
                )

            data = np.load(path, allow_pickle=False)
            kind = LAYERS[name]["kind"]
            entry: dict[str, Any] = {"kind": kind, "meta": _read_meta(data)}

            if kind in ("point", "pop"):
                entry["x"] = data["x"]
                entry["y"] = data["y"]
                entry["count"] = int(entry["x"].size)
                if kind == "pop":
                    entry["pop_f"] = data["pop_f"]
                    entry["pop_m"] = data["pop_m"]
            else:
                entry["wkb"] = data["wkb"]
                entry["offsets"] = data["offsets"]
                entry["bbox"] = data["bbox"]
                entry["count"] = int(entry["bbox"].shape[0])

            self._layers[name] = entry
            return entry

    def preload(self, names: Sequence[str] | None = None) -> None:
        for name in (names or LAYER_ORDER):
            try:
                self.get(name)
            except MissingCacheError:
                pass


def _read_meta(data: np.lib.npyio.NpzFile) -> dict[str, Any]:
    if "meta" not in data:
        return {}
    try:
        return ast.literal_eval(str(data["meta"]))
    except (ValueError, SyntaxError):
        return {}


# --------------------------------------------------------------------------
# per-kind band assignment
# --------------------------------------------------------------------------

def _bbox_mask(x: np.ndarray, y: np.ndarray, bounds: tuple[float, float, float, float],
               pool: np.ndarray) -> np.ndarray:
    """Indices of still-unassigned points inside a bounding box."""
    minx, miny, maxx, maxy = bounds
    mask = pool & (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
    return np.flatnonzero(mask)


def _assign_points(entry: dict[str, Any], bands: Sequence[Band],
                   with_population: bool) -> list[dict[str, Any]]:
    x, y = entry["x"], entry["y"]
    pool = np.ones(x.size, dtype=bool)
    results: list[dict[str, Any]] = []

    for band in bands:
        idx = _bbox_mask(x, y, band.geometry.bounds, pool)
        if idx.size:
            hit = shapely.intersects_xy(band.geometry, x[idx], y[idx])
            selected = idx[hit]
        else:
            selected = idx

        if with_population:
            female = float(entry["pop_f"][selected].sum(dtype=np.float64))
            male = float(entry["pop_m"][selected].sum(dtype=np.float64))
            results.append({
                "female": round(female, 1),
                "male": round(male, 1),
                "total": round(female + male, 1),
                "points": int(selected.size),
            })
        else:
            results.append({"count": int(selected.size)})

        pool[selected] = False

    return results


def _assign_lines(entry: dict[str, Any], bands: Sequence[Band]) -> list[dict[str, Any]]:
    wkb, offsets, bbox = entry["wkb"], entry["offsets"], entry["bbox"]
    pool = np.ones(bbox.shape[0], dtype=bool)
    results: list[dict[str, Any]] = []

    for band in bands:
        minx, miny, maxx, maxy = band.geometry.bounds
        mask = (pool
                & (bbox[:, 0] <= maxx) & (bbox[:, 2] >= minx)
                & (bbox[:, 1] <= maxy) & (bbox[:, 3] >= miny))
        candidates = np.flatnonzero(mask)

        hits: list[np.ndarray] = []
        for start in range(0, candidates.size, LINE_CHUNK):
            chunk = candidates[start:start + LINE_CHUNK]
            blobs = np.empty(chunk.size, dtype=object)
            for j, i in enumerate(chunk):
                blobs[j] = wkb[offsets[i]:offsets[i + 1]].tobytes()
            geoms = shapely.from_wkb(blobs)
            hits.append(chunk[shapely.intersects(geoms, band.geometry)])

        selected = np.concatenate(hits) if hits else np.empty(0, dtype=np.int64)
        results.append({"count": int(selected.size)})
        pool[selected] = False

    return results


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def analyze(store: LayerStore, bands: Sequence[Band],
            layers: Sequence[str] | None = None) -> dict[str, Any]:
    """Compute per-band and cumulative exposure for the requested layers.

    ``bands`` must already be dissolved and sorted strongest-first (which
    :func:`eqarc.dissolve.dissolve_bands` guarantees).
    """
    # A bare string would otherwise be iterated one character at a time.
    if isinstance(layers, str):
        layers = [layers]

    requested = [n for n in (layers or LAYER_ORDER) if n in LAYERS]
    unknown = [n for n in (layers or []) if n not in LAYERS]
    if not requested:
        raise ValueError(f"No valid layers requested. Unknown: {unknown}")

    # name -> list aligned with `bands`
    per_layer: dict[str, list[dict[str, Any]]] = {}
    timings: dict[str, float] = {}
    errors: dict[str, str] = {}

    for name in requested:
        started = time.perf_counter()
        try:
            entry = store.get(name)
            if entry["kind"] == "line":
                per_layer[name] = _assign_lines(entry, bands)
            else:
                per_layer[name] = _assign_points(
                    entry, bands, with_population=entry["kind"] == "pop")
        except MissingCacheError as exc:
            errors[name] = str(exc)
            continue
        timings[name] = round(time.perf_counter() - started, 3)

    ready = [n for n in requested if n in per_layer]

    band_rows = []
    for i, band in enumerate(bands):
        band_rows.append({
            "mmi_high": _clean_number(band.value),
            "mmi_low": _clean_number(band.attrs.get("mmi_low")),
            "color": band.attrs.get("color"),
            "area_km2": round(band.area_km2, 2),
            "geometry_stats": band.stats(),
            "elements": {name: per_layer[name][i] for name in ready},
        })

    return {
        "bands": band_rows,
        "cumulative": _cumulative(band_rows, ready),
        "totals": _sum_rows([r["elements"] for r in band_rows], ready),
        "layers_analyzed": ready,
        "layer_errors": errors,
        "timings_s": timings,
    }


def _clean_number(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _sum_rows(rows: Sequence[dict[str, Any]], layers: Sequence[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in layers:
        if LAYERS[name]["kind"] == "pop":
            female = sum(r[name]["female"] for r in rows)
            male = sum(r[name]["male"] for r in rows)
            out[name] = {
                "female": round(female, 1),
                "male": round(male, 1),
                "total": round(female + male, 1),
                "points": sum(r[name]["points"] for r in rows),
            }
        else:
            out[name] = {"count": sum(r[name]["count"] for r in rows)}
    return out


def _cumulative(band_rows: Sequence[dict[str, Any]],
                layers: Sequence[str]) -> list[dict[str, Any]]:
    """Running totals from the strongest band down: 'MMI >= X' exposure."""
    out = []
    for i, row in enumerate(band_rows):
        window = [r["elements"] for r in band_rows[: i + 1]]
        out.append({
            "mmi_min": row["mmi_high"],
            "area_km2": round(sum(r["area_km2"] for r in band_rows[: i + 1]), 2),
            "elements": _sum_rows(window, layers),
        })
    return out
