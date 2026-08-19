ALTER TABLE ai_job DROP CONSTRAINT IF EXISTS ai_job_workflow_check;
ALTER TABLE ai_job ADD CONSTRAINT ai_job_workflow_check
    CHECK (workflow IN ('catalog_query', 'agent_chat'));
