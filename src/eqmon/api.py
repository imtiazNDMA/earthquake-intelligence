"""FastAPI service. Loads the Vs30 grid once (cached) and serves filled MMI
contour bands per submitted event."""
from __future__ import annotations
import csv
import io
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import config, db
from .contours import mmi_to_geojson
from .export import featurecollection_to_shapefile_zip
from .events.ingest import ingest
from .events.repo import (count_events, create_manual_event, delete_event,
                           get_event, get_event_stats, list_events,
                           update_event, update_usgs_detail)
from .events.sources import METSource, USGSSource
from .impact import compute_event_impact
from .intensity import compute_mmi_grid
from .vs30 import Grid, load_grid

logger = logging.getLogger("uvicorn.error")

_ingest_scheduler_thread: threading.Thread | None = None
_STOP_SCHEDULER = False


def _ingest_sources() -> list[tuple[object, str]]:
    """Sources ingested each tick, in priority order. MET (Primary) goes first
    so it lands as the canonical row when it shares a quake with USGS."""
    return [(METSource(), "met_last_sync"), (USGSSource(), "usgs_last_sync")]


def _ingest_source(conn, source, sync_key: str) -> None:
    """Read last-sync, ingest one source, persist the new sync timestamp."""
    row = conn.execute(
        "SELECT value FROM _sync_state WHERE key = %s", (sync_key,)
    ).fetchone()
    updatedafter = datetime.fromisoformat(row[0]) if row is not None else None
    result = ingest(conn, source, updatedafter=updatedafter)
    conn.commit()
    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO _sync_state (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = now()",
        (sync_key, now_iso, now_iso),
    )
    conn.commit()
    logger.info("[scheduler] %s ingest: %d new, %d fetched",
                source.name, result.inserted, result.fetched)


def _ingest_tick() -> None:
    """One ingest cycle across all sources. A single source failing (network,
    parse, or DB) is logged and skipped so it never starves the others."""
    try:
        with db.get_conn() as conn:
            for source, sync_key in _ingest_sources():
                try:
                    _ingest_source(conn, source, sync_key)
                except Exception:
                    logger.exception("[scheduler] %s ingest failed", source.name)
    except Exception:
        logger.exception("[scheduler] ingest failed")


def _scheduler_loop(interval_sec: float) -> None:
    global _STOP_SCHEDULER
    _ingest_tick()  # one-shot on start
    while not _STOP_SCHEDULER:
        threading.Event().wait(interval_sec)
        if _STOP_SCHEDULER:
            break
        _ingest_tick()


def start_ingest_scheduler(interval_minutes: int = config.INGEST_INTERVAL_MINUTES) -> None:
    global _ingest_scheduler_thread
    if _ingest_scheduler_thread is not None and _ingest_scheduler_thread.is_alive():
        return
    _STOP_SCHEDULER = False
    _ingest_scheduler_thread = threading.Thread(
        target=_scheduler_loop, args=(interval_minutes * 60,), daemon=True,
    )
    _ingest_scheduler_thread.start()
    logger.info("[scheduler] started; ingesting MET+USGS every %d min",
                interval_minutes)


def stop_ingest_scheduler() -> None:
    global _STOP_SCHEDULER
    _STOP_SCHEDULER = True


@asynccontextmanager
async def _lifespan(_app):
    db.init_schema()
    start_ingest_scheduler()
    yield
    stop_ingest_scheduler()


app = FastAPI(title="Earthquake Intensity Platform", lifespan=_lifespan)


def _vs30_path() -> Path:
    return Path(os.environ.get("EQMON_VS30_TIF", str(config.VS30_TIF)))


@lru_cache(maxsize=1)
def get_grid() -> Grid:
    return load_grid(_vs30_path())


def reset_grid_cache() -> None:
    """Test hook: clear the cached grid so an env override takes effect."""
    get_grid.cache_clear()


class EventRequest(BaseModel):
    magnitude: float = Field(ge=0.0, le=10.0)
    depth_km: float = Field(ge=0.0, le=700.0)
    lat: float
    lon: float

    @field_validator("lat")
    @classmethod
    def _lat_in_region(cls, v):
        _, miny, _, maxy = config.COVERAGE_BBOX
        if not (miny <= v <= maxy):
            raise ValueError("latitude outside Coverage Region")
        return v

    @field_validator("lon")
    @classmethod
    def _lon_in_region(cls, v):
        minx, _, maxx, _ = config.COVERAGE_BBOX
        if not (minx <= v <= maxx):
            raise ValueError("longitude outside Coverage Region")
        return v


@app.post("/intensity")
def intensity(req: EventRequest) -> JSONResponse:
    grid = get_grid()
    mmi = compute_mmi_grid(
        grid.lon, grid.lat, grid.vs30,
        mag=req.magnitude, depth_km=req.depth_km,
        epi_lon=req.lon, epi_lat=req.lat,
    )
    fc = mmi_to_geojson(mmi, grid.transform, levels=config.MMI_BAND_LEVELS)
    # Persist to catalog silently so the event appears in the catalog /
    # impact endpoints. Best-effort — intensity bands render either way.
    try:
        with db.get_conn() as conn:
            row = create_manual_event(conn, magnitude=req.magnitude,
                                      depth_km=req.depth_km, lon=req.lon, lat=req.lat)
            conn.commit()
            fc["event_id"] = row["id"]
    except Exception:
        pass
    return JSONResponse(fc)


class FeatureCollectionIn(BaseModel):
    type: str
    features: list[dict]


@app.post("/intensity/export/shapefile")
def export_intensity_shapefile(fc: FeatureCollectionIn):
    if fc.type != "FeatureCollection" or not fc.features:
        raise HTTPException(status_code=400, detail="expected a non-empty FeatureCollection")
    try:
        data = featurecollection_to_shapefile_zip(fc.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=mmi_bands.shp.zip"},
    )


class ManualEvent(BaseModel):
    magnitude: float = Field(ge=0.0, le=10.0)
    depth_km: float = Field(ge=0.0, le=700.0)
    lat: float
    lon: float
    occurred_at: datetime | None = None

    @field_validator("lat")
    @classmethod
    def _lat_region(cls, v):
        _, miny, _, maxy = config.COVERAGE_BBOX
        if not (miny <= v <= maxy):
            raise ValueError("latitude outside Coverage Region")
        return v

    @field_validator("lon")
    @classmethod
    def _lon_region(cls, v):
        minx, _, maxx, _ = config.COVERAGE_BBOX
        if not (minx <= v <= maxx):
            raise ValueError("longitude outside Coverage Region")
        return v


@app.post("/events")
def create_event(ev: ManualEvent):
    with db.get_conn() as conn:
        row = create_manual_event(conn, magnitude=ev.magnitude, depth_km=ev.depth_km,
                                  lon=ev.lon, lat=ev.lat, occurred_at=ev.occurred_at)
        conn.commit()
    return row


@app.post("/events/ingest")
def ingest_events(min_magnitude: float | None = None):
    with db.get_conn() as conn:
        updatedafter = None
        row = conn.execute(
            "SELECT value FROM _sync_state WHERE key = 'usgs_last_sync'"
        ).fetchone()
        if row is not None:
            updatedafter = datetime.fromisoformat(row[0])
        result = ingest(conn, USGSSource(min_magnitude=min_magnitude),
                        updatedafter=updatedafter)
        conn.commit()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO _sync_state (key, value) VALUES ('usgs_last_sync', %s) "
            "ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = now()",
            (now_iso, now_iso),
        )
        conn.commit()
    return result.__dict__


@app.get("/events/ingest/status")
def ingest_status():
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM _sync_state WHERE key = 'usgs_last_sync'"
        ).fetchone()
        return {"last_sync": row[0] if row else None}

@app.get("/events")
def get_events(since: datetime | None = None,
               min_magnitude: float | None = None,
               max_magnitude: float | None = None,
               source: str | None = None,
               search: str | None = None,
               occurred_after: datetime | None = None,
               occurred_before: datetime | None = None,
               limit: int = 20,
               offset: int = 0,
               orderby: str = "time"):
    with db.get_conn() as conn:
        events = list_events(conn, since=since, min_magnitude=min_magnitude,
                             max_magnitude=max_magnitude, source=source,
                             search=search,
                             occurred_after=occurred_after,
                             occurred_before=occurred_before,
                             limit=limit, offset=offset,
                             orderby=orderby)
        total = count_events(conn, min_magnitude=min_magnitude,
                             max_magnitude=max_magnitude, source=source,
                             search=search,
                             occurred_after=occurred_after,
                             occurred_before=occurred_before)
        return {"total": total, "events": events}


@app.get("/events/export")
def export_events(format: str = "csv",
                  min_magnitude: float | None = None,
                  max_magnitude: float | None = None,
                  source: str | None = None,
                  search: str | None = None,
                  occurred_after: datetime | None = None,
                  occurred_before: datetime | None = None):
    with db.get_conn() as conn:
        evs = list_events(conn, min_magnitude=min_magnitude,
                          max_magnitude=max_magnitude, source=source,
                          search=search,
                          occurred_after=occurred_after,
                          occurred_before=occurred_before,
                          limit=None, orderby="time")
    if format == "geojson":
        features = []
        for e in evs:
            lon, lat = e.get("lon"), e.get("lat")
            if lon is None or lat is None:
                continue
            props = {k: v for k, v in e.items() if k not in ("lon", "lat") and v is not None}
            props["lon"] = lon
            props["lat"] = lat
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            })
        return JSONResponse(
            {"type": "FeatureCollection", "features": features},
            media_type="application/geo+json",
            headers={"Content-Disposition": "attachment; filename=events.geojson"},
        )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "source", "source_event_id", "occurred_at", "magnitude",
                "depth_km", "lon", "lat", "place", "mag_type", "alert",
                "tsunami", "sig", "review_status", "felt", "cdi", "mmi_report",
                "gap", "nst", "url", "detail_url"])
    for e in evs:
        w.writerow([e.get("id"), e.get("source"), e.get("source_event_id"),
                    e.get("occurred_at"), e.get("magnitude"), e.get("depth_km"),
                    e.get("lon"), e.get("lat"), e.get("place"), e.get("mag_type"),
                    e.get("alert"), e.get("tsunami"), e.get("sig"),
                    e.get("review_status"), e.get("felt"), e.get("cdi"),
                    e.get("mmi_report"), e.get("gap"), e.get("nst"),
                    e.get("url"), e.get("detail_url")])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=events.csv"},
    )


@app.get("/events/stats")
def event_stats():
    with db.get_conn() as conn:
        return get_event_stats(conn)

@app.get("/events/{event_id}")
def event_detail(event_id: int):
    with db.get_conn() as conn:
        row = get_event(conn, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="event not found")
    return row


@app.post("/events/{event_id}/impact")
def event_impact(event_id: int):
    with db.get_conn() as conn:
        event = get_event(conn, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        # read-only w.r.t. persisted tables; the ON COMMIT DROP temp table used
        # inside compute_event_impact is reclaimed by the pool's commit-on-exit.
        impact = compute_event_impact(conn, event, get_grid())
    return impact


@app.post("/events/{event_id}/refresh-from-usgs")
def refresh_from_usgs(event_id: int):
    with db.get_conn() as conn:
        event = get_event(conn, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        source_event_id = event.get("source_event_id")
        if not source_event_id:
            raise HTTPException(status_code=400,
                                detail="event has no source_event_id")
        detail = USGSSource().fetch_event(source_event_id)
        if detail is None:
            raise HTTPException(status_code=502,
                                detail="USGS FDSN request failed")
        updated = update_usgs_detail(conn, event_id, detail)
        conn.commit()
    return updated


class EventUpdate(BaseModel):
    magnitude: float | None = None
    depth_km: float | None = None
    lat: float | None = None
    lon: float | None = None
    place: str | None = None
    occurred_at: datetime | None = None


@app.put("/events/{event_id}")
def edit_event(event_id: int, body: EventUpdate):
    with db.get_conn() as conn:
        event = get_event(conn, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        updated = update_event(conn, event_id, magnitude=body.magnitude,
                                depth_km=body.depth_km, lon=body.lon,
                                lat=body.lat, place=body.place,
                                occurred_at=body.occurred_at)
        conn.commit()
    return updated


@app.delete("/events/{event_id}")
def remove_event(event_id: int):
    with db.get_conn() as conn:
        event = get_event(conn, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        ok = delete_event(conn, event_id)
        conn.commit()
    if not ok:
        raise HTTPException(status_code=500, detail="delete failed")
    return {"deleted": True, "id": event_id}


# serve the Leaflet frontend (built in a later task) at /
_web = Path(__file__).resolve().parents[2] / "web"
if _web.exists():
    app.mount("/", StaticFiles(directory=str(_web), html=True), name="web")
