CREATE INDEX IF NOT EXISTS seismic_event_geography_gix
    ON seismic_event USING GIST ((geom::geography));
