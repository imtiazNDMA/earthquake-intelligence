DELETE FROM seismic_event
WHERE source = 'PMD'
  AND occurred_at < TIMESTAMPTZ '1900-01-01 00:00:00+00';
