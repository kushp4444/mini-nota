-- Provider retries may retain a FunctionCall ID. A phase input gets a separate
-- execution-attempt identity; neither a provider ID nor time grants takeover.
ALTER TABLE execution_operations ADD COLUMN IF NOT EXISTS attempt_id text;
