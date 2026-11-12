# Explicit patient exclusion approval (#9)

`service.app.execute` now builds a complete selected-patient disposition report before scoring. QC privacy/malformed failures, mask failures and feature failures exclude scoring; missing/invalid outcomes exclude evaluation only. The report includes every selected identity, reasons, both eligibility lists and counts. Unaccounted identities fail explicitly. No eligible features terminates with `no_scoreable_patients`; clean runs bypass approval.

An exclusion emits `gate` with `status: waiting_approval`, the report and a compact numeric checkpoint. The processing task returns, engine subprocesses are finished, and terminal retention cleanup never expires pending gates. Other visitors can compute while this run waits. `POST /runs/:id/approve` requires the per-run Bearer secret and JSON `{disclosure_id, model_version}`. A control lock serializes approval/cancellation. The content hash binds selected cohort, model/feature versions, numeric measurements, disclosure generation and report. Approval rechecks the outcome join; changed exclusions produce a new gate and reject the old request. The score tool also checks `expected_eligibility` before computing any risk score, closing the revalidation-to-score gap. A changed join is re-disclosed. Repeated approval never launches duplicate scoring or reverses terminal state. Audit approval is an anonymous run action.

The initial plan payload includes immutable `model` metadata for browser History. Scoring preserves `scored.evaluation` as `run.evaluation`, emits a `tool_result` with `{stage:'evaluation',evaluation:...}`, and exposes it in snapshot/results. #8 consumes these without introducing new audit kinds.

## Browser and #13 restore contract

The gate card names every patient, scoring/evaluation disposition, reasons, counts and model version. Gate and approval events update saved status; existing `captureEvent` saves the checkpoint to IndexedDB alongside the opaque secret, patient selection and ordered event prefix. Reload reconnects and renders the same pending gate. The same-origin proxy permits `approve`.

`build_checkpoint(run, rows, report)` is the compact builder seam. Format version 1:

- `run_id`, `patient_ids`, `model_version`, `feature_version`, `generation`
- `feature_schema`: one ordered name array
- `feature_rows`: ordered `{patient_id, values: number[]}` records, each vector in schema order
- `eligibility`: complete report, including dispositions and static model metadata
- `disclosure_id`: SHA-256 of canonical JSON of the above fields (excluding ID/cursor)
- `last_sequence`: sequence of the gate event carrying this checkpoint

Numeric vectors avoid repeating 72 long feature names per patient, keeping full-library delivery compact. No browser-supplied path, artifact URL, executable model content or pickle is used. Secret and append-only audit prefix remain in the surrounding `SavedRun`; checkpoint does not copy either. #13 owns signing/validation across worker loss and restore endpoint/browser recovery. Restore should set `gate_generation` from checkpoint `generation`, reconstruct feature dictionaries by zipping schema with numeric values, validate exact schema/vector length/nonfinite values/library/model compatibility, preserve last sequence/events and secret, and resume only at pending approval. Current #12 worker-loss behavior still reports interrupted until #13 installs the agreed restore exception. There is no durable visitor server state.

## Verification

TDD red: original API failed the new mixed-exclusion test with terminal `failed`; score tool rejected the new expected-eligibility keyword before guard implementation. Real API fixtures exercise actual QC/mask/feature extraction and a development-trained frozen fixture model through HTTP subprocesses; fixtures are labeled and isolated in disposable Postgres schemas. Gate tests cover all exclusion stages, missing-outcome scoring, no silent drops, stale/duplicate approval, all-excluded terminal failure, other-visitor progress, cancellation terminality, changed outcome disclosure, and pending gates surviving short terminal retention. Browser fixtures verify disclosure/reload/approval/checkpoint retention and retain existing History/reconnection/cancellation coverage. No fixture is a full-library performance claim.

Final checks: 20 public API tests passed (77.95s), 2 model-tool tests passed, 24 browser tests passed (21.9s), and production Next build/TypeScript passed. A final two-test approval rerun verifies the added disclosure generation field. Browser checks use `WEB_URL=http://localhost:3099` (Next dev blocks 127.0.0.1-origin assets by default); own frontend process was stopped afterward. Integration tip 253df33 was already included before handoff. Existing dependency deprecation warnings remain.

## Integration verification

Merged into `codex/mini-nota-mvp` at `e2470c7`. The integrated public API and model-tool suites passed all **22 tests** (80.74 seconds), including exclusion accounting, changed disclosure, duplicate approval, cancellation, and indefinite pending-gate retention. The production frontend on isolated port 3099 passed all **25 browser checks** across approval, History, cancellation, reconnect, and catalog. `next build --webpack` and `tsc --noEmit` passed. The public real catalog still contains **82 patients and zero fixture rows**. Review confirmed that the score-worker eligibility guard is self-contained before #8 integration. No additional integration defect was found. The isolated frontend was stopped; root preview services were not restarted.
