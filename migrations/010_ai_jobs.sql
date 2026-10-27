CREATE TABLE IF NOT EXISTS ai_job (
    id BIGSERIAL PRIMARY KEY,
    workflow TEXT NOT NULL CHECK (workflow IN ('catalog_query')),
    workflow_version TEXT NOT NULL CHECK (btrim(workflow_version) <> ''),
    actor_id TEXT NOT NULL CHECK (btrim(actor_id) <> ''),
    role TEXT NOT NULL CHECK (role IN (
        'VIEWER', 'ANALYST', 'OPERATOR', 'REVIEWER', 'ADMINISTRATOR'
    )),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    request_fingerprint JSONB NOT NULL,
    result JSONB,
    model TEXT,
    usage JSONB,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CHECK ((status = 'completed') = (result IS NOT NULL)),
    CHECK ((status = 'failed') = (error_code IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ai_job_created_at_ix ON ai_job (created_at DESC);
CREATE INDEX IF NOT EXISTS ai_job_status_ix ON ai_job (status, created_at);
