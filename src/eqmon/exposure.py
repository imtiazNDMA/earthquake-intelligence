"""Adapter to ARC, the external elements-at-risk service.

ARC takes an MMI band layer and returns what sits under each band: population,
settlements, hospitals, schools, roads, bridges, airports. That is the half of
the impact picture `impact.py` cannot give — it rolls up *which admin units*
shake, not *what is inside* the shaking.

We proxy rather than letting the browser call ARC directly: it is an
unauthenticated Flask service on a Docker/WSL IP that moves, and a full analysis
is an expensive job we do not want reachable from the open page.

ARC's own vocabulary stops at this module's edge. It dissolves bands on a
`mmi_high` property; our domain name for that is `mmi_upper` (see contours.py).
`to_arc_bands` is the only place that translation lives.
"""
from __future__ import annotations

import asyncio
import copy
import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import config

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/exposure", tags=["exposure"])

# A full analysis walks every element layer (roads alone is ~375k features), so
# it is slow by nature — seconds, not milliseconds. The timeout is sized for the
# work, not for a typical HTTP hop.
_TIMEOUT = httpx.Timeout(config.ARC_TIMEOUT_S, connect=5.0)

_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def _get_client() -> httpx.AsyncClient:
    """Shared client for the *currently running* event loop.

    Same reasoning as buildings.py: an AsyncClient binds its pool to the loop
    that created it, and TestClient runs each request on a fresh one.
    """
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
        _client_loop = loop
    return _client


async def aclose() -> None:
    """Release the shared client. Called from the app lifespan shutdown."""
    global _client, _client_loop
    if _client is not None:
        await _client.aclose()
        _client = None
        _client_loop = None


def to_arc_bands(bands: dict) -> dict:
    """Our band FeatureCollection, spoken in ARC's dialect.

    ARC dissolves on `mmi_high` and rejects the layer outright without it. Our
    own properties ride along untouched so the payload stays recognisable in
    ARC's logs. The input is deep-copied: callers hand us the same bands they
    are about to render, and a shared mutation would leak ARC's field names into
    the map.
    """
    out = copy.deepcopy(bands)
    for feature in out.get("features", []):
        props = feature.setdefault("properties", {})
        props["mmi_high"] = props.get("mmi_upper")
        props["mmi_low"] = props.get("mmi_lower")
    return out


def _sum_elements(bands: list[dict]) -> dict:
    """Add up the element counts across bands.

    Sound only because ARC attributes each element to exactly one band — the
    highest it falls in — so bands never overlap and adding them cannot
    double-count.
    """
    out: dict[str, dict[str, float]] = {}
    for band in bands:
        for layer, values in (band.get("elements") or {}).items():
            acc = out.setdefault(layer, {})
            for field, value in values.items():
                if isinstance(value, (int, float)):
                    acc[field] = acc.get(field, 0) + value
    return out


def summarize(arc: dict, min_mmi: int = config.EXPOSURE_MIN_MMI) -> dict:
    """Reduce an ARC response to what the console shows.

    The headline is exposure at or above `min_mmi`, never `totals`. Our bands
    run down to MMI 2, which for a large event covers most of the country — the
    honest whole-footprint total is a nine-figure number no operator can act on.

    It is summed from the bands rather than read from ARC's `cumulative`,
    because the two disagree about what "MMI 6 and above" names. ARC keys
    `cumulative[].mmi_min` on a band's UPPER bound, so its 6 row includes the
    5-6 band; this platform labels a band by its LOWER bound (contours.py sets
    `label` from `mmi_lower`, and impact.py rolls up admin units the same way).
    Taking ARC's row directly would quietly fold all of MMI V into the MMI VI
    headline — on a real M7 that was 17.4M people instead of 9.4M. ARC's
    `cumulative` is passed through untouched for anyone who wants it, but the
    number the console leads with is computed here.
    """
    at_or_above = [b for b in arc.get("bands", []) if b.get("mmi_low", 0) >= min_mmi]
    headline = {
        "mmi_min": min_mmi,
        "area_km2": sum(b.get("area_km2", 0) for b in at_or_above),
        "elements": _sum_elements(at_or_above),
    }
    return {
        "min_mmi": min_mmi,
        "at_min_mmi": headline,
        "bands": arc.get("bands", []),
        "totals": arc.get("totals", {}),
        "cumulative": arc.get("cumulative") or [],
        "meta": arc.get("meta", {}),
    }


async def analyze(bands: dict, layers: list[str] | None = None) -> dict:
    """Run one MMI band layer through ARC and summarise the result."""
    if not bands.get("features"):
        # A small or deep event can fail to reach MMI 2 anywhere on the grid,
        # and an empty footprint still costs ARC a full scan of every layer to
        # come back with zeros. Answer it here, and say why it is empty.
        raise HTTPException(
            status_code=400,
            detail="no MMI bands to analyze: shaking does not reach MMI 2")

    payload: dict = {
        "source": "geojson",
        "geojson": to_arc_bands(bands),
        # We already render our own bands; ARC's smoothed copy would put a
        # second, subtly different footprint on the same map.
        "include_geometry": False,
    }
    if layers:
        payload["layers"] = layers

    url = f"{config.ARC_URL}/api/analyze"
    try:
        resp = await _get_client().post(url, json=payload)
    except Exception as exc:
        logger.warning("exposure: ARC unreachable at %s: %s", url, exc)
        raise HTTPException(status_code=503, detail="exposure service unavailable") from exc

    try:
        body = resp.json()
    except Exception:
        body = {}

    # ARC reports failure in the body as well as the status line, and the body
    # carries the reason — surface it rather than a bare 502.
    if resp.status_code != 200 or not body.get("ok"):
        reason = body.get("error") or f"ARC returned HTTP {resp.status_code}"
        logger.warning("exposure: ARC rejected the request: %s", reason)
        raise HTTPException(status_code=502, detail=f"exposure analysis failed: {reason}")

    return summarize(body)


class AnalyzeRequest(BaseModel):
    """An ad-hoc footprint, as produced by POST /intensity."""
    bands: dict = Field(..., description="MMI band FeatureCollection")
    layers: list[str] | None = Field(
        None, description="Element layers to count; omit for all of them")


@router.post("/analyze")
async def analyze_bands(req: AnalyzeRequest) -> dict:
    """Exposure for a footprint that is not in the catalog.

    The manual-event flow never persists an event, so it has no id to hang this
    off — it computes bands and asks about them directly.
    """
    return await analyze(req.bands, req.layers)


@router.get("/health")
async def health() -> dict:
    """Whether ARC is up and its caches are built.

    Never raises: the UI polls this to decide whether to offer exposure at all,
    so it has to get an answer even when ARC is down.
    """
    try:
        resp = await _get_client().get(f"{config.ARC_URL}/api/health")
        body = resp.json()
    except Exception as exc:
        logger.info("exposure: ARC health check failed: %s", exc)
        return {"available": False, "min_mmi": config.EXPOSURE_MIN_MMI}
    return {"available": True, "min_mmi": config.EXPOSURE_MIN_MMI, **body}


@router.get("/layers")
async def layers() -> dict:
    """The element layers ARC can count, and what each one measures."""
    try:
        resp = await _get_client().get(f"{config.ARC_URL}/api/layers")
        return resp.json()
    except Exception as exc:
        logger.warning("exposure: ARC layer list failed: %s", exc)
        raise HTTPException(status_code=503, detail="exposure service unavailable") from exc
