-- Run writer owns this schema. Never grant it to catalog/GraphQL readers.
CREATE TABLE IF NOT EXISTS visitor_runs (
 id text PRIMARY KEY,
 launch_nonce text UNIQUE,
 secret_digest text NOT NULL,
 document jsonb NOT NULL,
 revision bigint NOT NULL DEFAULT 0,
 cancel_intent boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS execution_operations (
 id text PRIMARY KEY,
 run_id text NOT NULL REFERENCES visitor_runs(id),
 phase text NOT NULL,
 generation integer NOT NULL,
 status text NOT NULL DEFAULT 'pending',
 owner text,
 fence bigint NOT NULL DEFAULT 0,
 submission_state text NOT NULL DEFAULT 'intent',
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(run_id,phase,generation)
);
CREATE TABLE IF NOT EXISTS operation_submissions (
 operation_id text NOT NULL REFERENCES execution_operations(id),
 submission_id text NOT NULL,
 provider_call_id text,
 ambiguous boolean NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(operation_id,submission_id)
);
CREATE TABLE IF NOT EXISTS run_events (
 run_id text NOT NULL REFERENCES visitor_runs(id),
 sequence bigint NOT NULL,
 event jsonb NOT NULL,
 PRIMARY KEY(run_id,sequence)
);
REVOKE ALL ON visitor_runs, execution_operations, operation_submissions, run_events FROM PUBLIC;
