CREATE TABLE IF NOT EXISTS run_launch_quota (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 visitor_digest text NOT NULL,
 accepted_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS run_launch_quota_visitor ON run_launch_quota (visitor_digest, accepted_at);
CREATE INDEX IF NOT EXISTS run_launch_quota_expiry ON run_launch_quota (accepted_at);
REVOKE ALL ON run_launch_quota FROM PUBLIC;
