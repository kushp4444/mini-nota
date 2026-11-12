# Live QC slice (#3)

`web/` is a Next.js TypeScript app deployable independently on Vercel. `/api/graphql` uses Apollo and reads PostgreSQL `patient_catalog`; the seed is explicitly development fixtures, not held-out membership. `DATABASE_URL` is required by Next. `scripts/seed_catalog.py` creates only catalog rows. Replace fixtures from the frozen partition when available.

Browser calls only same-origin `/api/*`. Next forwards allowlisted run routes to `RUNNER_URL` (external persistent service in production). No Python worker or run state lives in a Next global. `service.app` owns temporary in-memory runs and independent asyncio tasks; terminal runs expire after one hour. It never writes visitor data to PostgreSQL or disk. No run listing endpoint exists. `service.engine_api` invokes `EngineWorkspace` and requires `ENGINE_SECRET`; deploy on private network or firewall, never expose the secret to the browser. `RAW_DIR` identifies immutable prepared images.

Run API: POST `/runs` `{patient_ids:[...]}` => `{id,secret,status}`; GET `/runs/:id` and `/runs/:id/events?after=N` require `Authorization: Bearer <secret>`. SSE has stable `run_id:sequence` IDs and increasing sequences. GET snapshot excludes the secret and internal task. `after` supports reconnect without duplication. Events use `{id,run_id,sequence,timestamp,kind,message,payload}`. QC tool results put `{stage:'qc',patient:<EngineWorkspace patient contract>}` in payload. The UI consumes those values, not console prose. This slice explicitly terminates after QC; masks/features/scoring are not simulated.

## Local start

Use the root project's shared `.venv/bin/python` from this worktree. First install requirements, `npm ci --prefix web`, and import the real library with `python -m scripts.seed_catalog --prepared /path/data/processed/library-v1`. Only an isolated development database should use `python -m scripts.seed_catalog --fixtures`. PostgreSQL must be running.

```
ENGINE_SECRET=local-dev-secret RAW_DIR=/Users/kushpatel/Projects/mini-nota/data/raw python -m uvicorn service.engine_api:app --host 127.0.0.1 --port 8001
ENGINE_SECRET=local-dev-secret ENGINE_URL=http://127.0.0.1:8001 python -m uvicorn service.app:app --host 127.0.0.1 --port 8000
DATABASE_URL=postgresql://mini_nota@127.0.0.1:55432/mini_nota RUNNER_URL=http://127.0.0.1:8000 npm run dev --prefix web
```

Tests: `python -m pytest tests/test_service.py tests/test_engine.py -q`; `npm run build --prefix web`; with services/web running, `npm run test:e2e --prefix web`. API tests create/delete clearly marked synthetic catalog entries in real PostgreSQL and start a real private HTTP engine with generated DICOM. No SQLite substitute.

## Follow-on extension points

Add subsequent stages in `execute`, preserving per-patient accounting and tool result payloads. Engine artifacts must be copied into browser-retainable bytes before `EngineWorkspace` cleanup. A later cancellation slice should run active work in a tracked subprocess and terminate it; current HTTP QC invocation is not cancellable. Add cancel/approval proxy routes intentionally when implemented, rather than opening arbitrary backend paths. Browser persistence/reconnect/history is a later ticket; current History explicitly explains the limitation. Use IndexedDB for events, credentials, stage results, and artifacts, never durable server tables. The engine's pseudonym allowance is limited to known public Lung1 IDs matching directory and PatientID; unexpected names and birthdates still flag, including later slices, with no header values in errors.

## Verification at delivery

- `python -m pytest tests/test_service.py tests/test_engine.py -q`: 9 passed (real PostgreSQL and HTTP engine). Existing imaging dependencies emit deprecation/complex-cast warnings.
- `npm run build --prefix web` and strict TypeScript: passed.
- `npm audit --prefix web`: zero vulnerabilities after overriding the transitive GraphQL utility to patched 13.2.2.
- Root agent performed CUA browser smoke on the real local stack: selected three fixture patients, observed Running → Completed with all checks and 11 ordered audit events. Screenshot kept outside repository at `/private/tmp/mini-nota-implementation/qc-preview.png`.
- Playwright smoke source included; automated execution not yet run because Chromium installation remains in progress. This does not replace the completed live CUA check.
