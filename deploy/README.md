The current deployment path is [the Render/Modal runbook](modal-render-runbook.md); it supersedes the historical candidate below.

# Pre-migration release candidate (superseded hosting plan)

The owner subsequently chose a lightweight Render dispatcher, Neon metadata/features/results, R2 scans/saved results and Modal heavy execution, with Vercel frontend. That approved durable persistence supersedes the browser-only and single-host deployment guidance below. This document preserves the tested local baseline and candidate Linux tooling for adaptation; **do not provision from it as the new plan**. Architecture/spec updates are owned by the integration coordinator.

Status: local Darwin/arm64 verification is documented in `docs/ticket-15-handoff.md`. Public hosting and Linux extraction parity are release gates, not completed claims. Vercel is the chosen frontend; backend, asset storage and managed Postgres providers/credentials/resource budget still require the owner.

## Immutable data and database

Keep the frozen `cox-v1-a8e2738d012902a6f717` bundle, original prepared partition/outcomes and committed held-out evaluation. Do not rerun training or choose another split. There are 82 held-out patients (10,246 raw files, 5,459,320,394 logical bytes), 332 development patients, and 8 objective pre-partition exclusions from 422 inventoried sources. The serving raw mount needs only the 82 held-out patients. Packaging writes a fresh destination; no medical source images enter Git or the container image:

```bash
python -m scripts.release_assets create --prepared /prepared/library-v1 --bundle /models/cox-v1/model.json --destination /release/assets --output /release/manifest.json
cp /release/manifest.json /release/assets/manifest.json
python -m scripts.release_assets verify --root /release/assets --manifest /release/manifest.json --expected-sha256 THE_PRINTED_MANIFEST_SHA256
```

Retain the printed SHA256 in deployment configuration. The backend validates every file before listening; missing, changed, extra raw files or a development patient prevent startup. Mount `/release/assets` as `/assets:ro`; use a filesystem/volume with immutable versions and restrict its writer credentials to operators. An object store must materialize this verified read-only filesystem before starting the backend. Never use it for visitor output.

Initialize a **separate versioned** Postgres database with operator write credentials. Do not run these imports during web requests or with the serving login:

```bash
DATABASE_URL="$OPERATOR_DATABASE_URL" python -m scripts.seed_catalog --prepared /prepared/library-v1
DATABASE_URL="$OPERATOR_DATABASE_URL" python -m scripts.import_model --bundle /models/cox-v1/model.json
DATABASE_URL="$OPERATOR_DATABASE_URL" python -m scripts.import_evaluation --bundle /models/cox-v1/model.json --evaluation docs/held-out-evaluation-v1.json
psql "$OPERATOR_DATABASE_URL" -v database_name=mini_nota -v schema_name=public -f deploy/catalog-reader.sql
```

Create provider-managed serving login(s), grant `mini_nota_catalog_reader`, and set their own default transaction read-only (role settings are not inherited via membership). Give them no owner/admin membership and no schema CREATE. Configure provider-required TLS certificate verification and a supported connection pool endpoint for Node and Python; do not disable certificate validation. Validate SELECT/catalog API, and rejected INSERT/CREATE using the serving identity. The four immutable tables are `patient_catalog`, `catalog_metadata`, `model_metadata`, `model_evaluation`; there are no run/event/artifact tables.

## Linux image and numerical compatibility

`deploy/requirements-runtime.txt` pins the entire measured local environment, including the exact PyRadiomics Git commit. It is a candidate Linux resolution, **not** evidence Linux native wheels work. Do not replace model-sensitive versions. The Dockerfile defaults to the registry-verified official Python **3.14.7 slim-bookworm Linux amd64 manifest** `sha256:998acd06f485adfd6890e3e15a4b542543e0cf22ff904310095da328a5e3e561`. This digest was checked against the registry manifest bytes; the image has not yet been pulled/built locally. Use the explicit target CPU architecture. There is no floating fallback:

```bash
docker build --platform linux/amd64 --build-arg PYTHON_BASE=python@sha256:998acd06f485adfd6890e3e15a4b542543e0cf22ff904310095da328a5e3e561 -f deploy/Dockerfile -t mini-nota:release .
```

The builder creates all wheels, records their SHA256SUMS, then the final image installs those wheels offline, runs `pip check` and imports the native packages. Retain the built image digest, target platform, wheelhouse/SHA256SUMS and `/runtime-packages.txt` as operator release assets. Rebuilding against a package index can select a different platform wheel; reproduce the deployed image/wheelhouse digest rather than claiming package-version pins alone make bit-identical images. `libgl1`/`libglib2.0-0` are candidate OpenCV dependencies; only an actual target Linux build proves them sufficient.

Use the dispatchable Linux CI check to build and exercise synthetic fixtures first. Then run **actual new** LUNG1-002 extraction/scoring on the deployment architecture against the trusted immutable model. Confirm `feature_version=8128e4fb6ac580c2b4983326fa729203a488681c56c4ccceb8fe0cf1847d23e3` and compare all 72 ordered features and score with the prepared receipt. Matching version alone does not prove native numerical parity. The local score is 0.31620669544422614; document numerical tolerances before approving the target platform. Run the full real library on that platform before declaring the hosted demo verified.

## One backend owner and ephemeral execution

Run exactly **one replica and one uvicorn worker**. `python -m service.backend` owns runner and private loopback engine. The runner is the only externally reachable backend HTTP service; the browser accesses it through Next. The supervisor stops the entire unit when either service exits, including an unexpected exit 0. A lifetime pipe held only by the supervisor reaches every detached tool; EOF kills the tool's own group without scanning host processes or storing visitor PIDs durably. TERM has five seconds of service grace then escalation. Keep this entrypoint as container PID1; do not use `--pid=host`, multiple workers, or independently restart one service.

Configure `deploy/backend.env.example` through the provider secret manager, replacing every placeholder. Generate **one stable** cryptographic `CHECKPOINT_SIGNING_KEY` (at least 32 characters) and retain it across replacements for indefinite saved approval compatibility. Losing/rotating it invalidates old gates. Keep `ENGINE_SECRET` private to the backend and all secrets out of `NEXT_PUBLIC_*`, logs, Git and browser examples. Run secrets/checkpoints belong only in process memory and browser IndexedDB.

Docker invocation template (size parameters must follow measured target resources):

```bash
docker run --name mini-nota --read-only --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /run/mini-nota:rw,nosuid,nodev,uid=10001,gid=10001,mode=0700,size=1g \
  --mount type=bind,src=/release/assets,dst=/assets,readonly \
  --env-file /operator/backend.env -p 8000:8000 mini-nota:release
```

The example tmpfs size is a ceiling to validate, not a measured recommended allocation. Local sampled backend process-tree RSS already exceeded 2.3 GB, so a 2 GB host is insufficient before container/native/tmpfs overhead or concurrent visitors. Establish total RAM/CPU/concurrency from target measurements; an unanswered gate uses no tool process, but other visitors may compute independently. Tmpfs counts toward RAM and may swap: confirm provider swap is disabled/encrypted and that platform logs do not retain payloads before making a no-durable-artifact claim. SIGKILL cannot execute Python cleanup; PID namespace termination kills all remaining tools and disposal of the unit-private tmpfs removes files. Test both on the actual provider. The application emits no result-body access logs; retain no request/response-body tracing at the proxy/provider.

## Vercel frontend

Create/import the Git repository with **Root Directory `web`**, Next framework, Node **26.x**, `npm ci`, and `npm run build -- --webpack`. `web/vercel.json` records framework/build commands. Ship `web/public/examples` unchanged. Configure only server-side `RUNNER_URL=https://runner.example` and the read-only/pool/TLS `DATABASE_URL`; Vercel needs neither the engine secret nor checkpoint signing key. Choose a function region near Postgres/backend after providers are chosen.

Live computation spans many short requests: bounded `/event-page` polling (20 events by default), separate retained artifact downloads, compact numeric checkpoint POST. No function stays open for an approval deadline or the whole cohort. Restore POSTs are capped at 4,000,000 actual bytes in browser, Next and runner, below Vercel's documented 4.5 MB payload ceiling. Verify deployed event pages, largest artifact, GraphQL results, and full-cohort checkpoint body/response through Vercel; local development success does not establish hosted proxy limits. Authentication is an opaque per-run secret, not an account. Do not add user tracking or durable job tables.

## Release verification and outstanding gates

Run `python -m pytest tests -q` with local fixture Postgres, stable test signing key, bounded native threads. Run `npm ci`, `npm run build -- --webpack`, `npx tsc --noEmit`, then the **entire** `npx playwright test` harness from `web` against a configured production frontend + actual 82-patient catalog/runner/engine. `workflow.spec.ts`, scoring and evaluation are real-data checks; the other labeled fixture tests exercise browser failure/recovery. Never seed test patients over the frozen catalog; API fixtures create private schemas.

On the hosted target verify the full 82-patient run, single patient, clean/flagged/malformed/missing-outcome cases, confirmation/cancel, tool failure, runner+engine loss, cross-visitor independence, 20-year clock approval restoration, browser artifact durability with backend unavailable, terminal History, quota/unavailable storage, and no server visitor files after success/cancel/failure/replacement. Inspect representative overlays and observed KM steps. Retain only aggregate numerical/resource receipts and screenshots without visitor capabilities. Do not publish run-secret/checkpoint receipts or browser profiles.

Public deployment remains blocked until credentials/connections, providers, accepted resources/cost and actual Linux/image/provider verification exist. No public URL is provided by this local setup.
