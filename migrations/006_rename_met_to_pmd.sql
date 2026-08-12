-- Rename MET source to PMD across the database.
-- 1. Drop the old CHECK constraint (allows any source value temporarily)
-- 2. Update existing MET rows to PMD
-- 3. Add new CHECK constraint accepting 'PMD' instead of 'MET'
-- 4. Update sync_state keys

ALTER TABLE seismic_event DROP CONSTRAINT IF EXISTS seismic_event_source_check;

UPDATE seismic_event SET source = 'PMD' WHERE source = 'MET';

ALTER TABLE seismic_event ADD CONSTRAINT seismic_event_source_check
    CHECK (source IN ('PMD', 'USGS', 'MANUAL'));

UPDATE _sync_state SET key = 'pmd_last_sync' WHERE key = 'met_last_sync';
