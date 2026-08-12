"""Proxy to the external TileServerGL instance serving building footprints.

That server exposes one vector dataset per Pakistani district (161 of them),
each a tippecanoe-built .mbtiles with layer id "buildings". We proxy rather than
letting the browser hit it directly for two reasons: the upstream host is a WSL
IP that moves, and proxying keeps the frontend same-origin like every other
fetch in web/app.js.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException, Response

from . import config

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/buildings", tags=["buildings"])

MVT_MEDIA_TYPE = "application/vnd.mapbox-vector-tile"
_DATASET_SUFFIX = "_buildings"

# Tiles are large and requested in bursts (a pan can fire dozens). A shared
# async client with a generous connection pool keeps that off the threadpool.
_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None

# Upstream's catalog is static for the life of the server, so we fetch it once.
# It doubles as the allowlist for tile requests.
_catalog: list[dict] | None = None


def _get_client() -> httpx.AsyncClient:
    """Shared client for the *currently running* event loop.

    An AsyncClient binds its connection pool to the loop that created it. Under
    uvicorn there is only ever one loop, but TestClient runs each request on a
    fresh one, so a naively cached client raises "Event loop is closed" on the
    second call. Keying on the loop keeps one client per loop and makes the
    module safe under both.
    """
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=5.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )
        _client_loop = loop
    return _client


async def aclose() -> None:
    """Release the shared client. Called from the app lifespan shutdown."""
    global _client, _client_loop
    if _client is not None:
        await _client.aclose()
        _client = None
        _client_loop = None


def _label(dataset_id: str) -> str:
    """"Dera_Ghazi_Khan_buildings" -> "Dera Ghazi Khan"."""
    return dataset_id[: -len(_DATASET_SUFFIX)].replace("_", " ").strip()


def parse_catalog(index: list[dict]) -> list[dict]:
    """Reduce TileServerGL's /index.json to what the map needs.

    Keeps only building datasets, and only the fields the frontend uses. The
    `bounds` are the important part: they are what lets the layer manager
    activate just the districts intersecting the viewport instead of all 161.
    Entries without usable bounds are dropped — they cannot be gated, and
    loading them unconditionally is exactly what we are avoiding.
    """
    out: list[dict] = []
    for entry in index:
        dataset_id = entry.get("id") or ""
        if not dataset_id.endswith(_DATASET_SUFFIX):
            continue
        bounds = entry.get("bounds")
        if not (isinstance(bounds, (list, tuple)) and len(bounds) == 4):
            continue
        try:
            bounds = [float(v) for v in bounds]
        except (TypeError, ValueError):
            continue
        out.append({
            "id": dataset_id,
            "label": _label(dataset_id),
            "bounds": bounds,
            "maxzoom": entry.get("maxzoom", 17),
        })
    out.sort(key=lambda d: d["label"])
    return out


async def get_catalog() -> list[dict]:
    """Cached district catalog. Raises HTTPException(503) if upstream is down."""
    global _catalog
    if _catalog is not None:
        return _catalog
    url = f"{config.BUILDINGS_TILE_URL}/index.json"
    try:
        resp = await _get_client().get(url)
        resp.raise_for_status()
        index = resp.json()
    except Exception as exc:
        logger.warning("buildings: catalog fetch failed from %s: %s", url, exc)
        raise HTTPException(status_code=503, detail="buildings tile server unavailable") from exc
    _catalog = parse_catalog(index)
    logger.info("buildings: loaded %d district datasets from %s", len(_catalog), url)
    return _catalog


@router.get("/districts")
async def list_districts() -> dict:
    """District datasets available upstream, with bounds for viewport gating."""
    catalog = await get_catalog()
    return {"min_zoom": config.BUILDINGS_MIN_ZOOM, "districts": catalog}


@router.get("/tiles/{dataset}/{z}/{x}/{y}.pbf")
async def building_tile(dataset: str, z: int, x: int, y: int) -> Response:
    """Passthrough for one vector tile.

    `dataset` is checked against the catalog before any upstream request is
    made. Without that check this route would forward arbitrary user-supplied
    path segments to an internal host.
    """
    catalog = await get_catalog()
    if not any(d["id"] == dataset for d in catalog):
        raise HTTPException(status_code=404, detail="unknown building dataset")

    url = f"{config.BUILDINGS_TILE_URL}/data/{dataset}/{z}/{x}/{y}.pbf"
    try:
        resp = await _get_client().get(url)
    except Exception as exc:
        logger.warning("buildings: tile fetch failed %s: %s", url, exc)
        # 502 rather than 500: protomaps skips this tile, so one flaky district
        # degrades to holes in the render instead of killing the whole layer.
        raise HTTPException(status_code=502, detail="buildings tile fetch failed") from exc

    # 204/404 mean "no data in this tile" — extremely common at the edges of a
    # district's bounds, and not an error worth logging or rewriting.
    if resp.status_code in (204, 404):
        return Response(status_code=204)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="buildings tile fetch failed")

    # httpx has already transparently gunzipped the body (tileserver-gl serves
    # MVTs gzipped), so we hand back plain bytes and deliberately do NOT forward
    # the upstream Content-Encoding header — doing so would mislabel them.
    return Response(
        content=resp.content,
        media_type=MVT_MEDIA_TYPE,
        headers={"Cache-Control": "public, max-age=86400"},
    )
