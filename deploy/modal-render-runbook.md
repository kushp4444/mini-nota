# Render dispatcher and Modal phase worker

Use this runbook to deploy or update the ADR 0003 stack. See the [release checkpoint](../docs/release-checkpoint.md) for the verified deployment. For a new deployment, confirm account access, credits and billing before running provider commands.

## Runtime and limits

Vercel serves `web/` with server-only `RUNNER_URL=https://<Render service>` and a restricted catalog `DATABASE_URL`. Render uses `deploy/Dockerfile.dispatcher`/`deploy/render.yaml`, Free web service, one uvicorn process, `python -m service.dispatcher`; it contains no native imaging packages, compiler, scans, model bundle or local engine. `/health` never queries Neon or Modal. Render does not get source-bucket credentials. Missing configuration fails closed; there is no local heavy fallback. Its artifact route uses its own results-read credential after per-run capability authorization.

`modal_app.py` defines deployed app `mini-nota`, functions `run_phase` and manual `reconcile_pending`. `deploy/Dockerfile.modal` separately pins the Python 3.14.7 amd64 base, frozen numerical dependencies/PyRadiomics source revision, and Modal 1.6.4 plus resolved SDK dependencies. Stage the pinned manifest as ignored `deploy/worker-manifest.json`; the build copies only this small nonsecret configuration, never scans/model bytes. Keep its contents identical to the already verified manifest digest `afb52b9c96b756890f4050f0f3b02157bc2618fa4892dfd68cbd0f6f4b637217`. The worker downloads manifest-checked private R2 objects in up to eight concurrent requests and verifies every object before imaging. Preserve the original model `cox-v1-a8e2738d012902a6f717`, feature version `8128e4fb6ac580c2b4983326fa729203a488681c56c4ccceb8fe0cf1847d23e3` and 82 held-out identities.

Worker settings are defined in [modal_app.py](../modal_app.py). One input owns each single-use container, so termination targets that input's container. Platform crash redelivery cannot reclaim an already owned operation. Use the [hosted receipt](../docs/release-hosted-verification-v1.json) for measured elapsed time and sampled process memory, and the [Modal Function definition reference](https://modal.com/docs/sdk/py/latest/App) for resource fields.

There is **no enabled cron, warmup or idle database poll**. Accepted workers own their complete phase independently of Render/browser lifetime. Reconciliation runs once on dispatcher startup, launch/replay, authorized reconnect/control, or a manual operator command. A committed intent interrupted before provider acceptance waits for the next such trigger. That unavoidable dispatch-before-acceptance gap is not represented as completed/running compute. An optional external schedule requires a separate budget decision: frequent idle queries can prevent Neon scale-to-zero and consume its allowance. Do not add a keepalive to Render Free.

## Secrets and PostgreSQL setup

Create private files under `umask 077` outside Git, with 0600 permissions, using the three role-specific examples: `deploy/dispatcher.env.example`, `deploy/worker.env.example`, and `deploy/reconciler.env.example`. Existing `.env*` ignore coverage is available for local files; verify ignore status before filling them. Keep bootstrap `R2_UPLOAD_*`, owner URLs and deploy tokens in a separate operator file. Do not paste secrets into chat, argv, history, logs or screenshots. Retain a secure copy of the **same stable** `CHECKPOINT_SIGNING_KEY` across Render/worker/reconciler replacements; rotating it invalidates lost-response launch derivation and saved gate signatures.

Using the direct owner URL, create the versioned immutable catalog from the existing prepared library/model and import the committed held-out evaluation as documented in `deploy/README.md`. Do not retrain or regenerate the partition. Create SQL-restricted `catalog_reader` and `run_writer` runtime logins separately from the operator. Neon Console/API-created roles may carry `neon_superuser`; do not use them as restricted runtime roles. Own the `run_store` schema with a migration identity, not either serving login. Set **role-default** `search_path=run_store` for `run_writer` and `search_path=public` plus read-only for `catalog_reader`. Apply both migrations as the schema owner before starting runtime:

```bash
# RUN_DATABASE_URL here is the private direct schema-owner URL, loaded locally.
python -m scripts.init_run_store
# Then apply deploy/run-writer.sql as the owner with its documented psql variables.
```

`init_run_store` applies ordered idempotent migrations 001 and 002. Migration 002 adds the separate execution-attempt UUID. Runtime does no DDL. Grant the writer only schema USAGE and table SELECT/INSERT/UPDATE; deny schema CREATE and catalog modification. Grant the catalog reader only immutable catalog/model/evaluation SELECT; it must be denied the private run schema. Do not grant owner/admin memberships. Verify actual reader/writer privileges and current schema without printing connection strings. Use connect timeout 10 seconds and provider-supported TLS verification; never disable TLS certificate checks.

Neon transaction pooling must be verified with the actual endpoint and restricted role. Do not rely on request/session `SET search_path` or assume DSN `options=-c search_path=...` works through its pooler. This repository's local isolated-schema tests use a direct connection with `options`; they do not prove hosted pooler support. If role-default search path is not honored in a tested pooled connection, use a direct bounded runtime connection until qualified SQL/pooling is explicitly supported. Control locks are transaction-scoped PostgreSQL advisory locks, never human-waiting transactions.

Create two private R2 Standard buckets, public access off. Follow `deploy/r2.env.example` and `docs/ticket-17-handoff.md`: bootstrap source uploader read/write belongs only to the operator; worker source credential is read-only; worker results credential read/write; Render has a **different results-read-only** key. Run the reviewed `scripts.r2_assets` dry run first, then authorize its `--upload` separately after account activation and allowance inspection. The source contains 5,459,433,502 verified bytes; other account usage and retained artifacts consume additional storage. No browser bucket CORS is required for the existing authenticated artifact-byte proxy. Browser History continues saving actual bytes, not expiring links.

## Deploy after account and budget verification

Install `deploy/requirements-dispatcher.txt` in a dedicated operator environment for Modal CLI/definition verification. Keep the pinned native app environment separate. Authenticate Modal using the account's documented token flow; render gets a separate invocation token where the plan permits. Starter tokens are not assumed invoke-only; narrower RBAC/service-user capabilities may require another plan, which is not authorized here. Set `MODAL_APP_NAME=mini-nota` locally. After reviewing the private filtered files and selected Modal environment:

```bash
# These commands create remote secrets, builds and deployments.
modal secret create mini-nota-worker --env <environment> --from-dotenv <private-worker-env>
modal secret create mini-nota-reconciler --env <environment> --from-dotenv <private-reconciler-env>
# Copy the reviewed manifest only; do not copy source scans/model into deploy/.
cp <reviewed-release-assets-v1.json> deploy/worker-manifest.json
modal deploy --env <environment> modal_app.py
```

The two named Secrets must exist in that same Modal environment. Do not replace an existing Secret with `--force` without reviewing the change. Render's `MODAL_ENVIRONMENT` must select the same environment when it is not the SDK's default `main`. Configure Render's exact env values using `dispatcher.env.example` and its results-read token; import the Free Blueprint only after the human has reviewed it. Keep `autoDeployTrigger: off` during qualification. Vercel receives only its server-side runner URL and catalog-reader URL, neither Modal/R2 nor operator credentials. Redeploy after changing its env targets.

Provider builds and invocations may consume credits. Before any build/canary, the human must inspect [Modal budgets](https://modal.com/docs/guide/budgets), current credits and plan, and verify a custom **$0 net spend limit if the account accepts it**, plus a gross usage limit within its actual credit allowance. Docs do not establish a universally accepted minimum numeric limit. Gross usage budgets apply before credits; net spend limits apply after credits. R2 activation requires human checkout/terms and its allowance is **not** an enforceable $0 spend cap. Confirm [Render Free](https://render.com/docs/free), [Neon Free/scale to zero](https://neon.com/docs/introduction/scale-to-zero), [R2 pricing](https://developers.cloudflare.com/r2/pricing/), [Modal pricing](https://modal.com/pricing), and Vercel Hobby eligibility against the actual accounts. Public unbounded traffic cannot be promised free by these software limits.

## Operation and recovery

A launch commits a stable imaging operation before spawning via the Modal SDK. Each worker obtains its **actual** `current_function_call_id()`, generates a fresh attempt UUID, and atomically claims the pending operation before importing native code or loading scans. Duplicate claims fail even with the same provider call ID and never compute. Ownership has no lease/timeout takeover. Every stage boundary and publication checks its call/attempt/fence and cancellation state. Actual progress/features/events go to Neon, verified binary artifacts to R2 before completion; no CT bytes enter Render, PostgreSQL or Modal arguments/returns.

An imaging input executes QC → masks → features → eligibility and either scores a clean run or persists a signed gate and returns. A gate has no deadline and holds no compute. Modal approval records the exact persisted cohort/model disclosure without requiring a local engine. The new scoring input downloads only verified static files (`scans=False`), validates the frozen feature/model contract and rechecks expected eligibility against those immutable outcomes **before scoring**; a changed report opens another gate rather than silently scoring. Duplicate approvals create only one logical continuation. Local development retains the original HTTP eligibility recheck.

Cancellation first persists its tombstone. Render then reconstructs and terminates **all known** owned/submitted phase inputs using `FunctionCall.from_id(...).cancel(terminate_containers=True)`, including a gate-return tail. It reports canceled only after every known call acknowledges termination. Unknown accepted inputs cannot claim the tombstoned operation. Provider outage leaves retryable `canceling`; retry the same authorized cancel/reconnect after recovery. The worker independently watches durable cancellation while native work runs, kills its own process group/descendants and cleans scratch even when Render cannot contact Modal. The native child's inherited lifetime pipe also kills that group when its input owner dies abruptly. Provider/container disposal owns scratch cleanup after SIGKILL.

Accepted-but-lost submit responses retain an ambiguous registration and the same logical operation. Reconciliation waits at least 30 seconds between unknown-ID retries, with at most three registrations. A self-registering worker supplies its owner ID despite a lost response. After the final grace period, an operation with no known call or owner fails with an audit reason and fences late claims. A known submitted call is never resubmitted automatically. Confirmed stopped or expired input without a durable gate or terminal result is terminated and recorded as an interrupted failure, preserving prior results. Transport and authentication errors alone do not establish that work stopped. Provider reconstruction, nonblocking polling and container termination use the documented [FunctionCall SDK](https://modal.com/docs/sdk/py/latest/FunctionCall).

Saved results and artifacts never depend on [Modal output retention](https://modal.com/docs/guide/job-queue) (currently up to seven days). Read terminal runs through capability-authorized API even after provider output expiration/outage. There is no public visitor-run listing. For committed pending/cancel intents after a dispatcher failure, reconnect/startup retries or an operator may invoke one bounded pass:

```bash
# With only the private reconciler credentials loaded locally:
python -m scripts.reconcile_runs
# Or invoke the deployed lightweight function, without an enabled schedule:
modal run --env <environment> modal_app.py::reconcile_pending
```

A failed artifact upload preserves earlier committed results and ends explicitly failed. Upload-before-commit may leave unreferenced objects; do not delete retained referenced artifacts on restart. No automatic bucket lifecycle or retention deletion was enabled.

## Qualify a deployment

Build both images on Linux and check the pinned dependencies and lightweight dispatcher. Verify provider permissions and budget controls. On the target stack, exercise a real single-patient run, cancellation acknowledgement, ambiguous spawn, restart recovery, gate approval and saved result access. For a change to the image or numerical runtime, compare all 72 newly extracted Linux features, the feature version and the frozen score to the recorded contract. Use the frozen full 82-patient run when qualifying a cohort-scale change, and record the elapsed time, sampled memory, usage and numerical differences. Link the evidence from the [release checkpoint](../docs/release-checkpoint.md).
