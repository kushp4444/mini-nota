# Durable run ownership and saved results (#16)

`RUN_DATABASE_URL` activates durable anonymous runs independently of the immutable `CATALOG_DATABASE_URL`/`DATABASE_URL` reader. Apply `python -m scripts.init_run_store` as the schema owner first; runtime performs no DDL. [Migration/grants](../migrations/README.md) and `deploy/run-writer.sql` describe a private schema with separate run-writer/catalog-reader privileges. No account, session identity or public visitor-run listing was added. PostgreSQL stores capability **digests**, pinned model/feature context, selected patients, dispositions, approval checkpoints, actual extracted features, structured results, ordered audit and execution identities. It rejects `data_base64` and binary transport. Browser History continues retaining downloaded bytes locally.

`service.run_repository.RunRepository` is the trusted API/worker boundary. It imports psycopg and standard library only; `service.app` imports no imaging/native modules. All publications lock the run row, compare its revision, append unique/consecutive audit rows and commit the snapshot/results in one transaction. Worker publications also check exact operation owner/fence and durable cancellation intent. Selected cohort/model context is immutable, stage patient identities are unique, terminal state cannot be revived, and gate/terminal completion finishes its operation. Failed artifact uploads roll back the in-memory unpublished snapshot before recording an explicit failure, preserving earlier committed results.

Launch nonce → opaque run ID and a capability derived with the stable operator signing key allow a lost-response retry after replacement to recover the same receipt; only its digest is stored. Duplicate selection mismatches are rejected. Losing/rotating that key requires deliberate migration and invalidates derivation for launch replay. Authorized saved results/events/artifact routes reconstruct from PostgreSQL after a fresh OS process starts. Terminal records have no temporary retention timeout. Existing valid browser-saved v1 gates remain importable: the verifier accepts the previous raw-secret HMAC and the new digest-bound HMAC. New workers can sign gates from a stored digest without recovering a capability. A gate has no deadline, holds no worker, and approval revalidates its disclosed eligibility/model before atomically creating exactly one scoring intent.

## #18 execution adapter contract

Logical phases are `imaging` generation 0, then `scoring` with the exact `gate_generation`. `create(run,nonce)` commits a pending imaging operation with the run. `publish(run,approve=True)` commits approval audit/state plus the unique scoring intent atomically. Importing a historical gate creates **no** compute intent until approval. Local execution remains the default and uses the existing private cancellable HTTP engine; `EXECUTION_BACKEND=deferred` deliberately leaves intent for an external adapter/reconciler (tests/bootstrap seam, not a deployed Modal implementation).

Use the stable logical operation throughout dispatch uncertainty:

```python
repo = RunRepository(writer_url)
# Dispatcher: private, bounded queue; do not expose this as an HTTP run listing.
for intent in repo.pending(limit=20):
    # If cancel_intent, reconcile cancellation rather than submitting work.
    # Commit/record submission identity, then spawn with intent['id'].
    repo.register_submission(intent['id'], submission_id, ambiguous=True)
    # Record the actual returned provider ID if/when known; retries use the same
    # logical operation, never a fresh phase/generation.
    repo.register_submission(intent['id'], submission_id, provider_call_id)

# Worker FIRST action, before scans/native imports/computation:
fence = repo.claim(operation_id, current_provider_call_id)
if fence is None:
    return  # duplicate/terminal/canceling/stale phase: no heavy work
context = repo.operation_context(operation_id)
run = context['run']  # private snapshot, revision and secret DIGEST; no capability
run['_operation'] = {'id': operation_id, 'owner': current_provider_call_id, 'fence': fence}
# Use the orchestration policy in service.app.execute / score_run; #18 replaces
# HTTP tool invocation with its worker-local native adapter and verified assets.
# service.app.emit externalizes binary artifacts, then calls:
repo.publish(run, operation=run['_operation'])
```

`operation(run_id,phase,generation)` retrieves a phase identity. `operation_context(operation_id)` bootstraps a trusted worker, `active_owners(run_id)` identifies calls requiring stop, and `submissions(operation_id)` reads registrations for provider reconciliation, and `register_submission` retains every dispatch registration including ambiguous provider acceptance. Worker self-registration supplies the owner even if the dispatcher dies after provider acceptance and before recording its response. Only one concurrent claim succeeds, including duplicate claims by the same provider ID. There is **no timer/lease takeover**. Query the provider before any reconciliation; `reconcile_stopped(operation_id,owner,fence)` marks a matching owner interrupted **only after external proof of stop/termination**. It never retries/reassigns that worker. If interrupted outside cancellation, #18 must surface an explicit interrupted failure (or a deliberately new fenced continuation) rather than silently leaving/stealing live work.

Cancellation persists its intent/status **before** awaiting stop. Subsequent claims and worker publications fail closed. The current local adapter confirms process termination through the private engine and only then records canceled. A nonlocal owner remains `canceling`/503 until provider stop is confirmed; local engine acknowledgement cannot stand in for Modal termination. #18 must implement provider cancellation/retry/reconciliation, then conditionally record the stopped/terminal outcome. A pending unclaimed input is blocked by the tombstone even if delivered later. Committed intent that has not reached the provider waits for the next reconciler; independent wake/scheduling is #18/release work, and is not claimed here.

Control serialization uses a **transaction-scoped advisory lock** with nonblocking attempts, so it works with transaction poolers while allowing other runs to proceed. A transaction spans only an individual control request/eligibility verification, never human waiting. Use bounded connection/provider timeouts in deployment.

## Artifact boundary and delivery

`emit` uses #17 `ArtifactStore.from_env(role='results')`, uploading under an operation/fence/event/index identity before metadata publication. It stores `object_ref` privately. Public run/SSE/event-page output removes that reference/key and exposes only the existing capability-authorized artifact route. That route loads only its persisted run-owned metadata and validates bytes through `ArtifactStore.read`; browser-supplied keys are never accepted. Uncommitted uploads may be collected later; retained referenced artifacts must survive dispatcher replacement. Production uses `R2_RESULTS_*`; `LOCAL_ARTIFACT_DIR` explicitly enables the private filesystem adapter only for local development. Never configure that directory as durable storage on Render.

## Verification

All API tests use unique actual PostgreSQL schemas and actual small DICOM/RTSTRUCT fixture processing; no fixture is a measured full-library result. The integrated storage case runs original application Python/Pydantic with a **separate local Moto HTTP process**, not a cloud account:

```bash
MOTO_SERVER_PYTHON=/private/tmp/mini-nota-17-fixture-venv/bin/python \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /Users/kushpatel/Projects/mini-nota/.venv/bin/python -m pytest tests -q
```

The explicit bridge selector is `tests/test_durable_runs.py::test_real_s3_artifacts_survive_replacement_with_private_capability_access`. The `MOTO_SERVER_PYTHON` interpreter is created from `deploy/requirements-storage-fixture.txt`; CI now runs the same integrated durable API tests from the original image interpreter while only the Moto server uses the isolated environment. `deploy/Dockerfile` includes the migrations. Without that explicit interpreter, the ordinary app suite labels/skips the S3-integrated case rather than pretending cloud verification.

Verified behaviors include fresh dispatcher OS-process receipt/results/artifact recovery; concurrent launches; duplicate approvals with one score; indefinite persisted gates; cancellation/late-publication fencing; eight competing worker claims; ambiguous submission/self-registration; remote-cancel stop uncertainty; explicit upload failure with earlier results retained; legacy browser gate import; and real separate reader/writer roles (catalog reader denied visitor state; runtime writer has no DDL rights). Actual S3 adapter API proof verifies PNG checksum, unauthenticated/cross-run rejection, private reference removal, fresh-process byte retrieval and retained bytes after both servers stop. Browser regressions separately verify IndexedDB History/downloaded bytes, cancellation/reconnect and approval.

Latest full integrated Python checkpoint: **81 passed**, including the actual S3 HTTP adapter, on the original application runtime. Production Next build/TypeScript passed; **28** targeted History/cancellation/reconnect/approval browser checks passed. Final targeted durable verification and commits are reported at handoff. Frozen model/data/82-patient catalog are unchanged. No Modal SDK, account provisioning, paid resources, cloud availability, deployed Linux numerical parity or zero-cost claim is included. #18 owns the actual remote scheduling/native execution and provider cancellation/reconciliation.
