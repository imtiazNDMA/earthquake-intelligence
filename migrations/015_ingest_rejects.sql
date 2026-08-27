CREATE TABLE IF NOT EXISTS ingest_reject (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('PMD', 'USGS')),
    source_event_id TEXT,
    reason_code TEXT NOT NULL CHECK (reason_code IN (
        'invalid_record_shape',
        'missing_event_id',
        'missing_coordinates',
        'invalid_coordinates',
        'coordinate_out_of_range',
        'missing_magnitude',
        'invalid_magnitude',
        'magnitude_out_of_range',
        'missing_origin_time',
        'invalid_origin_time',
        'origin_time_before_minimum',
        'origin_time_in_future',
        'invalid_depth',
        'outside_coverage'
    )),
    parser_version TEXT NOT NULL CHECK (btrim(parser_version) <> ''),
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    source_record JSONB NOT NULL,
    retrieval_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seen_count BIGINT NOT NULL DEFAULT 1 CHECK (seen_count > 0),
    UNIQUE (source, parser_version, reason_code, payload_sha256)
);

CREATE INDEX IF NOT EXISTS ingest_reject_last_seen_ix
    ON ingest_reject (last_seen_at DESC);
CREATE INDEX IF NOT EXISTS ingest_reject_reason_ix
    ON ingest_reject (source, reason_code, last_seen_at DESC);
