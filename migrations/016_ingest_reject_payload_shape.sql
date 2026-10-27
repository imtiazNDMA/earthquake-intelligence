ALTER TABLE ingest_reject
    DROP CONSTRAINT ingest_reject_reason_code_check;

ALTER TABLE ingest_reject
    ADD CONSTRAINT ingest_reject_reason_code_check CHECK (reason_code IN (
        'invalid_payload_shape',
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
    ));
