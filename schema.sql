CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS seismic_event (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL CHECK (source IN ('MET', 'USGS', 'MANUAL')),
    source_event_id TEXT,
    occurred_at     TIMESTAMPTZ NOT NULL,
    magnitude       DOUBLE PRECISION NOT NULL,
    depth_km        DOUBLE PRECISION NOT NULL,
    geom            geometry(Point, 4326) NOT NULL,
    cluster_id      BIGINT,
    is_canonical    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS seismic_event_source_uq
    ON seismic_event (source, source_event_id)
    WHERE source_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS seismic_event_geom_gix ON seismic_event USING GIST (geom);
CREATE INDEX IF NOT EXISTS seismic_event_time_ix ON seismic_event (occurred_at);

CREATE TABLE IF NOT EXISTS admin_boundary (
    id         BIGSERIAL PRIMARY KEY,
    level      TEXT NOT NULL CHECK (level IN ('national','province','district','tehsil')),
    name       TEXT NOT NULL,
    parent     TEXT,
    division   TEXT,
    population DOUBLE PRECISION,
    geom       geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS admin_boundary_geom_gix ON admin_boundary USING GIST (geom);
CREATE INDEX IF NOT EXISTS admin_boundary_level_ix ON admin_boundary (level);
