CREATE INDEX IF NOT EXISTS seismic_event_geog_gix
    ON seismic_event USING GIST ((geom::geography));
CREATE INDEX IF NOT EXISTS seismic_event_mainshock_ix
    ON seismic_event (is_mainshock);
