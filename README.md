# Mini-Nota

**Architecture migration checkpoint:** the owner has now selected Vercel + Render Free dispatcher + Neon Free + Cloudflare R2 + Modal Functions, with saved results in Neon/R2. The implementation and measurements below describe the pre-migration browser-local baseline. The durable PostgreSQL run store is available through `RUN_DATABASE_URL`; remote Modal execution and hosted verification remain pending; `deploy/` preserves the earlier single-host candidate and must not be treated as the new deployment plan.

Mini-Nota is an unauthenticated public-data imaging workflow demonstration: select held-out Lung1 patients, inspect scan checks, tumor masks, 72 radiomic measurements and frozen-model risk rankings, and review the actual tool calls and decisions. Patients, Analysis, browser-local History and immediately viewable curated examples share a NOTA-inspired workspace. This independent project is not affiliated with Altis Labs, a medical device or medical advice.

The actual prepared collection contains 422 inventoried patients, 8 objective pre-partition processing exclusions and 414 usable patients. The frozen split has **332 development / 82 held-out** patients; only held-out patients are selectable, all selected by default. Live execution never trains a model. Model **`cox-v1-a8e2738d012902a6f717`** uses a fixed development reference for percentiles and higher/lower model-risk groups. Its independent 82-patient held-out Harrell c-index is **0.6057961981925833**, with 95% patient-bootstrap interval **[0.5326564103414366, 0.6739709514124799]**. These finite-cohort results do not establish clinical validity. Scores and percentiles are relative rankings, not death probabilities or lifespans.

Next.js/TypeScript supplies the browser UI, GraphQL and same-origin control proxy. The default local runner invokes a private FastAPI imaging engine. Set `RUN_DATABASE_URL` after applying the [durable run migration](migrations/README.md) to retain run ownership, ordered audit, features, gate checkpoints and saved results in PostgreSQL across dispatcher replacement. Artifacts use verified object references through the R2 storage seam; local development may explicitly configure `LOCAL_ARTIFACT_DIR`. Keep catalog-reader and run-writer credentials separate. There is no public visitor-run listing or account identity.

Browser IndexedDB also retains terminal results and downloaded artifact bytes. A stable operator signing key permits valid existing browser-saved approval checkpoints to resume without a gate deadline. Closing a tab does not cancel work; confirmed cancellation stops the owned tool. Clearing browser data loses local History and its private run capabilities. Without `RUN_DATABASE_URL`, the original temporary local-runner behavior remains available for development. Remote execution and provider reconciliation are delivered separately by #18; a restarted local dispatcher never steals an operation whose worker may still be alive.

## Local setup

Use CPython **3.14.7** and the recorded measurement versions. Install requirements together; the exact measured candidate runtime is in `deploy/requirements-runtime.txt`:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r deploy/requirements-runtime.txt
cd web
npm ci
```

Obtain and prepare the public dataset using [data/README.md](data/README.md), [preparation handoff](docs/ticket-6-handoff.md), [model handoff](docs/ticket-7-handoff.md) and [evaluation handoff](docs/ticket-8-handoff.md). Large source/prepared images and model bundles are ignored by Git. Keep the existing frozen partition/model unchanged when reproducing this release. Import catalog, model and evaluation explicitly with operator database credentials, then serve using a separate read-only identity as described in [deploy/README.md](deploy/README.md).

Configure backend environment using [deploy/backend.env.example](deploy/backend.env.example): `DATABASE_URL`, `RAW_DIR`, `MODEL_BUNDLE`, `OUTCOMES_CSV`, private `ENGINE_SECRET` and a stable random `CHECKPOINT_SIGNING_KEY` of at least 32 characters. Keep keys outside Git. From the repository root:

```bash
.venv/bin/python -m service.backend
```

Configure `web/.env.local` from [web/.env.example](web/.env.example), using the read-only database and `RUNNER_URL=http://127.0.0.1:8000`. From `web`, run `npm run dev`; production verification uses `npm run build -- --webpack` then `npm run start`. No secrets need a `NEXT_PUBLIC_` prefix. Static curated examples remain viewable even without a live backend and explicitly identify introduced fixture faults.

## Verification and deployment

```bash
# Repository root; fixture Postgres configured via DATABASE_URL.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m pytest tests -q
# web/; production frontend and actual held-out backend running.
npm run build -- --webpack
npx tsc --noEmit
WEB_URL=http://localhost:3000 npx playwright test
```

API tests isolate their PostgreSQL schemas. Browser tests label synthetic fixtures; workflow/scoring/evaluation checks require the real 82-patient catalog and immutable imaging/model assets. No synthetic result is a full-library performance measurement.

See [release runbook](deploy/README.md) for the Vercel frontend, read-only database initialization, immutable held-out-only asset manifest, pinned Linux image build, single-owner supervisor, tmpfs cleanup, payload bounds and hosted verification gates. See [release evidence](docs/ticket-15-handoff.md) for measured local execution and precise external blockers. Public deployment and Linux numerical parity require actual target verification before the demo is declared ready.

The original offline CLI (`python -m src.pipeline`) remains available for development; its legacy survival fitting is separate from the hosted frozen-model workflow. Numerical geometry, measurement and survival behavior are documented in `docs/ticket-4-handoff.md` through `docs/ticket-8-handoff.md`.
