"""Render the PGA return-period rasters into map-ready PNG overlays.

The source grids are float32 GeoTIFFs of peak ground acceleration in g, one per
return period (data/PGA/). A browser cannot read a GeoTIFF, and at 347x250 the
grids are far too small to be worth tiling — so each is classified into its five
published bands and written as an RGBA PNG that Leaflet drops on the map as an
image overlay, with a manifest carrying the bounds and the legend.

Classification is *not* computed here. The breaks and colours below are read off
data/PGA/PGA_Return_Period_Legend.png, the legend that ships with the data, and
each return period has its own breaks. Re-deriving them (equal interval, quantile,
Jenks) would produce a map that disagrees with the published hazard maps these
grids came from, which is the one thing this layer must not do.

Output (web/pga/, gitignored — regenerate with this script):
  pga_<rp>.png    RGBA overlay, transparent where the grid has no data
  manifest.json   bounds + legend for the frontend

Usage:
  uv run python scripts/build_pga_overlays.py
"""
from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 — pins PROJ
import numpy as np  # noqa: E402
import rasterio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "PGA"
OUT = ROOT / "web" / "pga"

# Shared five-step ramp, sampled from the supplied legend PNG.
RAMP = ["#006100", "#7aab00", "#ffff00", "#ff9900", "#ff2200"]

# Per return period: source file, and the upper bound + printed label of each
# band. Upper bounds are inclusive; the last band catches everything above.
# Filenames are inconsistent in the source drop (.tif.tif on three of them);
# they are named literally rather than globbed so a rename is a loud failure.
PERIODS = [
    {"rp": 95, "file": "PGA_Return_Period_95.tif",
     "breaks": [0.13, 0.20, 0.27, 0.39],
     "labels": ["0.04 – 0.13", "0.14 – 0.20", "0.21 – 0.27", "0.28 – 0.39", "0.40 – 0.56"]},
    {"rp": 475, "file": "PGA_Return_Period_475.tif.tif",
     "breaks": [0.28, 0.39, 0.46, 0.60],
     "labels": ["0.11 – 0.28", "0.29 – 0.39", "0.40 – 0.46", "0.47 – 0.60", "0.61 – 0.99"]},
    {"rp": 975, "file": "PGA_Return_Period_975.tif.tif",
     "breaks": [0.33, 0.46, 0.57, 0.69],
     "labels": ["0.16 – 0.33", "0.34 – 0.46", "0.47 – 0.57", "0.58 – 0.69", "0.70 – 1.21"]},
    {"rp": 2475, "file": "PGA_Return_Period_2475.tif.tif",
     "breaks": [0.36, 0.44, 0.62, 0.78],
     "labels": ["0.25 – 0.36", "0.37 – 0.44", "0.45 – 0.62", "0.63 – 0.78", "0.79 – 1.49"]},
]

# Probability of exceedance in 50 years, the way a return period is usually read
# aloud. 475 yr is the design-level shaking in most building codes.
EXCEEDANCE = {95: "41% in 50 yr", 475: "10% in 50 yr",
              975: "5% in 50 yr", 2475: "2% in 50 yr"}


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _write_png(path: Path, rgba: np.ndarray) -> None:
    """Write an RGBA PNG. Hand-rolled to avoid a Pillow dependency for one call.

    PNG is a sequence of length-prefixed, CRC-checked chunks over a zlib stream
    of scanlines, each prefixed with a filter byte (0 = none).
    """
    height, width = rgba.shape[:2]
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    # bit depth 8, colour type 6 (RGBA), deflate, adaptive filter, no interlace
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(raw, 9))
                     + chunk(b"IEND", b""))


def _classify(values: np.ndarray, mask: np.ndarray, breaks: list[float]) -> np.ndarray:
    """Grid of PGA -> RGBA, transparent outside the data."""
    # searchsorted with the four interior breaks yields band indices 0..4.
    idx = np.searchsorted(np.asarray(breaks, dtype="float32"), values, side="left")
    palette = np.array([_hex_to_rgb(c) for c in RAMP], dtype="uint8")
    rgba = np.zeros(values.shape + (4,), dtype="uint8")
    rgba[..., :3] = palette[np.clip(idx, 0, len(RAMP) - 1)]
    # Fully opaque here; the frontend controls overlay opacity, so baking a
    # partial alpha in would compound with it.
    rgba[..., 3] = np.where(mask, 0, 255)
    return rgba


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Source not found: {SRC}")
    OUT.mkdir(parents=True, exist_ok=True)

    bounds = None
    entries = []
    for spec in PERIODS:
        path = SRC / spec["file"]
        if not path.exists():
            raise SystemExit(f"Source not found: {path}")
        with rasterio.open(path) as src:
            band = src.read(1, masked=True)
            b = src.bounds
        # All four grids share one extent; the frontend places every overlay with
        # a single box, so a mismatch would silently misregister one of them.
        extent = [round(v, 6) for v in (b.left, b.bottom, b.right, b.top)]
        if bounds is None:
            bounds = extent
        elif extent != bounds:
            raise SystemExit(f"{path.name} extent {extent} != {bounds}")

        rgba = _classify(band.filled(0).astype("float32"),
                         np.ma.getmaskarray(band), spec["breaks"])
        out_png = OUT / f"pga_{spec['rp']}.png"
        _write_png(out_png, rgba)

        entries.append({
            "return_period": spec["rp"],
            "label": f"{spec['rp']}-year",
            "exceedance": EXCEEDANCE[spec["rp"]],
            "image": f"pga/pga_{spec['rp']}.png",
            "legend": [{"color": c, "label": l}
                       for c, l in zip(RAMP, spec["labels"])],
        })
        cells = int((~np.ma.getmaskarray(band)).sum())
        print(f"  pga_{spec['rp']}.png  {out_png.stat().st_size / 1024:.1f} KB  "
              f"{rgba.shape[1]}x{rgba.shape[0]}  {cells} data cells")

    manifest = {"bounds": bounds, "unit": "g", "periods": entries}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"  manifest.json  bounds={bounds}")


if __name__ == "__main__":
    main()
