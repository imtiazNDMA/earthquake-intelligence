CREATE TABLE IF NOT EXISTS analysis_artifact (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (
        kind IN ('intensity', 'impact', 'exposure', 'analytics', 'aftershock')
    ),
    schema_version TEXT NOT NULL CHECK (btrim(schema_version) <> ''),
    calculation_version TEXT NOT NULL CHECK (btrim(calculation_version) <> ''),
    input_hash TEXT NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
    computation_input JSONB NOT NULL CHECK (jsonb_typeof(computation_input) = 'object'),
    data_fingerprint JSONB NOT NULL CHECK (jsonb_typeof(data_fingerprint) = 'object'),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    provenance JSONB NOT NULL CHECK (jsonb_typeof(provenance) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (kind, schema_version, calculation_version, input_hash)
);

CREATE OR REPLACE FUNCTION reject_analysis_artifact_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'analysis artifacts are immutable'
        USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS analysis_artifact_immutable ON analysis_artifact;
CREATE TRIGGER analysis_artifact_immutable
BEFORE UPDATE OR DELETE ON analysis_artifact
FOR EACH ROW EXECUTE FUNCTION reject_analysis_artifact_mutation();
