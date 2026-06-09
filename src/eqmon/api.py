"""FastAPI service. Loads the Vs30 grid once (cached) and serves filled MMI
contour bands per submitted event."""
from __future__ import annotations
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import config, db
from .contours import mmi_to_geojson
from .events.ingest import ingest
from .events.repo import create_manual_event, get_event, list_events
from .events.sources import USGSSource
from .impact import compute_event_impact
from .intensity import compute_mmi_grid
from .vs30 import Grid, load_grid

app = FastAPI(title="Earthquake Intensity Platform")


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
    return JSONResponse(fc)


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
def ingest_events():
    with db.get_conn() as conn:
        result = ingest(conn, USGSSource())
        conn.commit()
    return result.__dict__


@app.get("/events")
def get_events(since: datetime | None = None, min_magnitude: float | None = None,
               limit: int = 100):
    with db.get_conn() as conn:
        return list_events(conn, since=since, min_magnitude=min_magnitude, limit=limit)


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
        impact = compute_event_impact(conn, event, get_grid())
    return impact


# serve the Leaflet frontend (built in a later task) at /
_web = Path(__file__).resolve().parents[2] / "web"
if _web.exists():
    app.mount("/", StaticFiles(directory=str(_web), html=True), name="web")
