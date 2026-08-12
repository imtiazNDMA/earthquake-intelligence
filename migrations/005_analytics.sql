ALTER TABLE seismic_event ADD COLUMN IF NOT EXISTS is_mainshock BOOLEAN;
ALTER TABLE seismic_event ADD COLUMN IF NOT EXISTS sequence_id  BIGINT;
ALTER TABLE seismic_event ADD COLUMN IF NOT EXISTS zone_id      BIGINT;

CREATE TABLE IF NOT EXISTS tectonic_zone (
    id   BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    geom geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS tectonic_zone_geom_gix ON tectonic_zone USING GIST (geom);
CREATE INDEX IF NOT EXISTS seismic_event_zone_ix  ON seismic_event (zone_id);
