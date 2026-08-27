CREATE TABLE IF NOT EXISTS analysis_claim (
    id BIGSERIAL PRIMARY KEY,
    schema_version TEXT NOT NULL CHECK (schema_version = '1.0'),
    claim_type TEXT NOT NULL CHECK (claim_type IN (
        'modeled_event_maximum_mmi_class',
        'modeled_admin_maximum_mmi_class',
        'modeled_admin_representative_mmi'
    )),
    entity_type TEXT NOT NULL CHECK (
        entity_type IN ('seismic_event', 'admin_boundary')
    ),
    entity_id BIGINT NOT NULL CHECK (entity_id > 0),
    display_name TEXT NOT NULL CHECK (btrim(display_name) <> ''),
    value NUMERIC NOT NULL CHECK (
        value::text NOT IN ('NaN', 'Infinity', '-Infinity')
    ),
    unit TEXT NOT NULL CHECK (unit IN ('mmi_class', 'mmi')),
    source_kind TEXT NOT NULL CHECK (
        source_kind IN ('intensity', 'impact', 'exposure', 'analytics', 'aftershock')
    ),
    source_artifact_id BIGINT NOT NULL REFERENCES analysis_artifact(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    source_path TEXT NOT NULL CHECK (
        source_path ~ '^/(computation_input|data_fingerprint|payload|provenance)(/([^~/]|~[01])*)+$'
    ),
    source_artifact_schema_version TEXT NOT NULL CHECK (
        btrim(source_artifact_schema_version) <> ''
    ),
    calculation_version TEXT NOT NULL CHECK (btrim(calculation_version) <> ''),
    observed_at TIMESTAMPTZ,
    freshness INTERVAL CHECK (
        freshness IS NULL OR freshness >= INTERVAL '0 seconds'
    ),
    limitation TEXT CHECK (limitation IS NULL OR btrim(limitation) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (
        schema_version, source_artifact_id, claim_type,
        entity_type, entity_id, source_path
    )
);

CREATE INDEX IF NOT EXISTS analysis_claim_source_artifact_ix
    ON analysis_claim (source_artifact_id);

CREATE OR REPLACE FUNCTION validate_analysis_claim_artifact()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    artifact_kind TEXT;
    artifact_schema_version TEXT;
    artifact_calculation_version TEXT;
BEGIN
    SELECT kind, schema_version, calculation_version
      INTO artifact_kind, artifact_schema_version, artifact_calculation_version
      FROM analysis_artifact
     WHERE id = NEW.source_artifact_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'source analysis artifact % does not exist', NEW.source_artifact_id
            USING ERRCODE = '23503';
    END IF;
    IF NEW.source_kind <> artifact_kind THEN
        RAISE EXCEPTION 'claim source kind does not match analysis artifact'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.source_artifact_schema_version <> artifact_schema_version THEN
        RAISE EXCEPTION 'claim schema version does not match analysis artifact'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.calculation_version <> artifact_calculation_version THEN
        RAISE EXCEPTION 'claim calculation version does not match analysis artifact'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION reject_analysis_claim_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'analysis claims are immutable'
        USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS analysis_claim_validate_artifact ON analysis_claim;
CREATE TRIGGER analysis_claim_validate_artifact
BEFORE INSERT ON analysis_claim
FOR EACH ROW EXECUTE FUNCTION validate_analysis_claim_artifact();

DROP TRIGGER IF EXISTS analysis_claim_immutable ON analysis_claim;
CREATE TRIGGER analysis_claim_immutable
BEFORE UPDATE OR DELETE ON analysis_claim
FOR EACH ROW EXECUTE FUNCTION reject_analysis_claim_mutation();
