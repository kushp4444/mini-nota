# Durable run store

Apply `python -m scripts.init_run_store` with `RUN_DATABASE_URL` set to the schema-owner connection before starting the dispatcher. Ordered migrations 001 and 002 are idempotent and does not touch `patient_catalog`, model/evaluation tables, scans or the frozen bundle. Runtime startup does not run DDL. Neon supports these ordinary PostgreSQL tables, row locks and transactions; no extension is required. Use TLS and provider-supported connection settings in deployment.

Use a dedicated schema (for example `run_store`) owned by a migration role, a `run_writer` login for the API/worker and an independent `catalog_reader` login for `CATALOG_DATABASE_URL` (Next GraphQL uses its existing `DATABASE_URL`). The runtime run-writer role must have its run schema as the default search path. Verify it on the actual Neon endpoint; transaction poolers may reject DSN `options` and must not depend on session SET. Local direct-connection tests use `options` only for isolated schemas. The catalog connection must have no access to that schema. Example grants, executed by an operator after creating the roles and schema:

```sql
REVOKE ALL ON SCHEMA run_store FROM PUBLIC, catalog_reader;
GRANT USAGE ON SCHEMA run_store TO run_writer;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA run_store TO run_writer;
REVOKE ALL ON ALL TABLES IN SCHEMA run_store FROM PUBLIC, catalog_reader;
-- Give catalog_reader only the immutable deployed catalog tables:
GRANT USAGE ON SCHEMA public TO catalog_reader;
GRANT SELECT ON public.patient_catalog, public.model_metadata, public.model_evaluation TO catalog_reader;
```

Do not reuse a schema-owner/admin connection for the frontend catalog role. `visitor_runs` contains only a SHA-256 capability digest, never the raw control capability; worker ownership and audit are private writer data. There is no public run-list endpoint. The capability returned on launch is deterministically derived from the opaque run ID and stable `CHECKPOINT_SIGNING_KEY`, which permits replay after a lost response. Retain that key across replacements; rotating it changes new launch replay credentials, so perform a deliberate migration rather than silently rotating it.

Runs use a JSONB snapshot for pinned model/feature context, dispositions, gate checkpoints, extracted features and structured results; ordered audit events also have a unique `(run_id, sequence)` key. Revisions, row locks, operation fences and cancellation intent make snapshot/audit publication atomic. Binary content and `data_base64` are rejected by the repository; only verified object references enter PostgreSQL. Terminal records have no ephemeral runner retention expiry. Browser History still saves downloaded artifact bytes locally.

Local development can set `LOCAL_ARTIFACT_DIR` to a private persistent test directory. This explicit filesystem adapter is unsuitable for Render's ephemeral disk. Production uses #17's `R2_RESULTS_*` storage configuration. Object uploads happen before publication; failed transactions can leave unreferenced objects for later collection. Never collect referenced objects merely because a dispatcher restarts.
