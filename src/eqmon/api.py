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
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from . import buildings, config, db, exposure
from .ai import client as ai_client
from .aftershock_service import EventNotFoundError, compute_forecast
from .analytics_service import EmptyCatalogError, compute_analytics
from .contours import mmi_to_geojson
from .export import featurecollection_to_shapefile_zip
from .events.ingest import ingest
from .events.repo import (catalog_coverage, count_events,
                           create_manual_event, delete_event, get_event,
                           list_events, update_event, update_usgs_detail)
from .events.search import EVENT_SEARCH_SCHEMA_VERSION, EventSearchSpec
from .events.sources import PMDSource, USGSSource
from .impact import compute_event_impact
from .intensity import compute_mmi_grid
from .vs30 import Grid, get_grid, reset_grid_cache

logger = logging.getLogger("uvicorn.error")

_ingest_scheduler_thread: threading.Thread | None = None
_STOP_SCHEDULER = False
_pmd_tick_counter = 0
_INGEST_LOCK = threading.Lock()


def _ingest_sources() -> list[tuple[object, str]]:
    """Sources for this tick. USGS runs every tick (1 min). PMD (full-catalog)
    runs every Nth tick (config.PMD_INTERVAL_MULTIPLIER). PMD goes first when it
    runs so it lands as the canonical row when it shares a quake with USGS."""
    global _pmd_tick_counter
    _pmd_tick_counter = (_pmd_tick_counter + 1) % 1_000_000
    sources: list[tuple[object, str]] = []
    if _pmd_tick_counter % config.PMD_INTERVAL_MULTIPLIER == 0:
        sources.append((PMDSource(), "pmd_last_sync"))
    sources.append((USGSSource(), "usgs_last_sync"))
    return sources


def _ingest_source(conn, source, sync_key: str) -> None:
    """Read last-sync, ingest one source, persist the new sync timestamp."""
    row = conn.execute(
        "SELECT value FROM _sync_state WHERE key = %s", (sync_key,)
    ).fetchone()
    updatedafter = datetime.fromisoformat(row[0]) if row is not None else None
    result = ingest(conn, source, updatedafter=updatedafter)
    _commit_successful_ingest(conn, sync_key, result)
    logger.info("[scheduler] %s ingest: %d new, %d fetched",
                source.name, result.inserted, result.fetched)


def _commit_successful_ingest(conn, sync_key: str, result) -> None:
    if result.errors:
        conn.rollback()
        raise RuntimeError("ingest failed: " + "; ".join(result.errors))
    sync_dt = getattr(result, "watermark", None) or datetime.now(timezone.utc)
    sync_iso = sync_dt.isoformat()
    conn.execute(
        "INSERT INTO _sync_state (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = now()",
        (sync_key, sync_iso, sync_iso),
    )
    conn.commit()


def _raise_ingest_error(exc: RuntimeError) -> None:
    raise HTTPException(status_code=502, detail=str(exc))


def _acquire_ingest_or_409() -> None:
    if not _INGEST_LOCK.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="another ingest is already running; try again shortly",
        )


def _ingest_tick() -> None:
    """One ingest cycle across all sources. A single source failing (network,
    parse, or DB) is logged and skipped so it never starves the others."""
    if not _INGEST_LOCK.acquire(blocking=False):
        logger.info("[scheduler] ingest skipped; another ingest is already running")
        return
    try:
        with db.get_conn() as conn:
            for source, sync_key in _ingest_sources():
                try:
                    _ingest_source(conn, source, sync_key)
                except Exception:
                    logger.exception("[scheduler] %s ingest failed", source.name)
    except Exception:
        logger.exception("[scheduler] ingest failed")
    finally:
        _INGEST_LOCK.release()


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
    logger.info("[scheduler] started; ingesting PMD+USGS every %d min",
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
    await buildings.aclose()
    await exposure.aclose()
    ai_client.close()


app = FastAPI(title="Earthquake Intensity Platform", lifespan=_lifespan)

# Registered here — well above the /{full_path:path} SPA fallback at the bottom
# of this module, which would otherwise swallow /buildings/* and /exposure/*.
app.include_router(buildings.router)
app.include_router(exposure.router)


class EventRequest(BaseModel):
    magnitude: float = Field(ge=0.0, le=10.0)
    depth_km: float = Field(ge=0.0, le=700.0)
    lat: float
    lon: float
    save_to_catalog: bool = False

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
    # Opt-in: only persist to the catalog when the caller asks. Keeps ad-hoc
    # "what-if" calculations from cluttering the event catalog. Best-effort —
    # intensity bands render either way.
    if req.save_to_catalog:
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
        headers={"Content-Disposition": "attachment; filename=mmi_bands.zip"},
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
    _acquire_ingest_or_409()
    try:
        with db.get_conn() as conn:
            updatedafter = None
            row = conn.execute(
                "SELECT value FROM _sync_state WHERE key = 'usgs_last_sync'"
            ).fetchone()
            if row is not None:
                updatedafter = datetime.fromisoformat(row[0])
            result = ingest(conn, USGSSource(min_magnitude=min_magnitude),
                            updatedafter=updatedafter)
            try:
                _commit_successful_ingest(conn, "usgs_last_sync", result)
            except RuntimeError as exc:
                _raise_ingest_error(exc)
    finally:
        _INGEST_LOCK.release()
    return result.__dict__


@app.post("/events/ingest/pmd")
def ingest_pmd_events():
    """Manually pull the PMD (Primary) feed. PMD returns the
    full catalog each call; ingest() upserts and re-clusters (PMD wins as
    canonical over USGS for shared quakes)."""
    _acquire_ingest_or_409()
    try:
        with db.get_conn() as conn:
            result = ingest(conn, PMDSource())
            try:
                _commit_successful_ingest(conn, "pmd_last_sync", result)
            except RuntimeError as exc:
                _raise_ingest_error(exc)
    finally:
        _INGEST_LOCK.release()
    return result.__dict__


@app.get("/events/ingest/status")
def ingest_status():
    with db.get_conn() as conn:
        rows = dict(conn.execute(
            "SELECT key, value FROM _sync_state "
            "WHERE key IN ('usgs_last_sync', 'pmd_last_sync')"
        ).fetchall())
        usgs = rows.get("usgs_last_sync")
        pmd = rows.get("pmd_last_sync")
        # last_sync = most recent across sources (kept for the existing UI label)
        last = max([t for t in (usgs, pmd) if t], default=None)
        return {"last_sync": last, "usgs_last_sync": usgs, "pmd_last_sync": pmd}

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


@app.post("/events/search")
def search_events(spec: EventSearchSpec):
    """Search the deterministic catalog contract used by UI and future AI."""
    filters = spec.model_dump()
    with db.get_conn() as conn:
        events = list_events(conn, **filters)
        count_filters = {
            key: value for key, value in filters.items()
            if key not in {"limit", "offset", "orderby"}
        }
        total = count_events(conn, **count_filters)
        coverage = catalog_coverage(conn)
    return {
        "schema_version": EVENT_SEARCH_SCHEMA_VERSION,
        "query": spec.model_dump(mode="json"),
        "distance_semantics": (
            "geodesic distance from the supplied WGS84 point to each event point"
            if spec.radius_km is not None else None
        ),
        "event_kind_semantics": (
            "mainshocks and aftershocks include only explicitly classified rows; "
            "unclassified rows appear only when event_kind is all"
        ),
        "source_semantics": (
            "source filters canonical catalog rows; superseded source observations "
            "are not returned"
        ),
        "catalog_coverage": {
            **coverage,
            "completeness": "not_asserted",
        },
        "total": total,
        "events": events,
    }


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


@app.get("/zones")
def zones():
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, ST_AsGeoJSON(geom) FROM tectonic_zone"
        ).fetchall()
    import json
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"zone_id": r[0], "name": r[1]},
         "geometry": json.loads(r[2])} for r in rows]}


@app.get("/analytics")
def analytics(window: str = "1y", min_mag: str = "mc",
              zone_id: int | None = None, bbox: str | None = None):
    """Catalog analytics for one slice. The computation lives in
    `analytics_service` so tools and schedulers can reach it without HTTP."""
    with db.get_conn() as conn:
        try:
            return compute_analytics(conn, window=window, min_mag=min_mag,
                                     zone_id=zone_id, bbox=bbox)
        except EmptyCatalogError:
            raise HTTPException(status_code=404, detail="empty catalog")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


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


class ExposureQuery(BaseModel):
    layers: list[str] | None = Field(
        None, description="Element layers to count; omit for all of them")


@app.post("/events/{event_id}/exposure")
async def event_exposure(event_id: int, req: ExposureQuery | None = None):
    """Elements at risk under a catalog event's shaking footprint.

    Deliberately separate from /impact: that one answers "which admin units
    shake" from PostGIS, this one answers "what is inside the shaking" from ARC.
    They are computed independently and one being unavailable must not take the
    other down.
    """
    with db.get_conn() as conn:
        event = get_event(conn, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")

    grid = get_grid()
    mmi = compute_mmi_grid(
        grid.lon, grid.lat, grid.vs30,
        mag=event["magnitude"], depth_km=event["depth_km"],
        epi_lon=event["lon"], epi_lat=event["lat"],
    )
    bands = mmi_to_geojson(mmi, grid.transform, levels=config.MMI_BAND_LEVELS)
    return await exposure.analyze(bands, req.layers if req else None)


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


class AftershockRequest(BaseModel):
    event_id: int | None = None
    magnitude: float | None = None
    lat: float | None = None
    lon: float | None = None


@app.post("/aftershock")
def aftershock_endpoint(req: AftershockRequest) -> JSONResponse:
    """Compute aftershock probabilities for a given event.

    Provide *event_id* (fetched from catalog) **or** inline
    *magnitude* + *lat* + *lon*.  Region is auto-detected from
    the tectonic-zone spatial lookup, falling back to lat bands.
    """
    with db.get_conn() as conn:
        try:
            result = compute_forecast(conn, event_id=req.event_id,
                                      magnitude=req.magnitude,
                                      lat=req.lat, lon=req.lon)
        except EventNotFoundError:
            raise HTTPException(status_code=404, detail="event not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(result)


# Serve static frontend files — defined AFTER all API routes so they take priority.
_web = Path(__file__).resolve().parents[2] / "web"


def _serve_file(path: str) -> FileResponse:
    """Resolve a path under the web root, falling back only for SPA routes."""
    root = _web.resolve()
    cleaned = path.replace("\\", "/").lstrip("/")
    candidate = (root / cleaned).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=404, detail="not found")
    if candidate.exists() and candidate.is_file():
        return FileResponse(str(candidate))

    first_segment = cleaned.split("/", 1)[0]
    if first_segment in {"assets", "tiles"} or Path(cleaned).suffix:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(root / "index.html"))


if _web.exists():
    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str = ""):
        return _serve_file(full_path)
