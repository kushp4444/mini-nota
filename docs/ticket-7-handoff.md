# Frozen development model and live scoring (#7)

The real development-only model is frozen at **`cox-v1-a8e2738d012902a6f717`**. Its ignored bundle is `/Users/kushpatel/Projects/mini-nota/data/processed/models/cox-v1/model.json`; the committed `docs/model-v1-manifest.json` records its exact file/content checksums, 72 ordered inputs, measurement contract, and partition checksum. Do not recreate the partition or tune against the held-out patients.

## Development and artifact contract

`src.frozen_model.train_model(prepared, destination)` uses only the frozen 332 development patients. Five deterministic observed-event-stratified folds (seed 1729) compare Cox L2 penalties `[0.01, 0.1, 1, 10]` using validation concordance. Every fold fits its own variable-feature filter (population standard deviation >1e-12), standard scaling, and Cox model; the winning penalty, **10**, is refit on all 332 development patients. All 72 features remain variable in that final fit. No held-out result influenced preprocessing, penalty selection, or the split.

The JSON bundle contains ordered input schema, extraction contract/version, fitted filter/means/scales/Cox coefficients/centering, complete frozen partition, exact CV membership/settings/results, preparation provenance/input checksums, library versions, 332 sorted development reference log-risk scores and their fixed median. It contains numeric fitted parameters rather than executable pickle content. Integrity checks reject changed bundles. `risk_score` is **log partial hazard relative to the fitted development center**; it is a relative ordering, not survival probability or lifespan. Negative scores are valid. A contiguous per-row numerical reduction ensures exact batch/one-patient equality.

`feature_version` hashes the ordered schema, radiomics YAML, source bytes of `dicom_loader.py`, `masks.py`, and `extract_features.py`, and NumPy/PyRadiomics/SimpleITK/pydicom/rt-utils versions. It excludes orchestration, display, and `EngineWorkspace` source, so control/UI work does not invalidate measurements. Offline training verifies the prepared provenance matches that extraction contract; actual measurement changes require preparation and fitting again. Live feature results carry this version, and `FrozenModel.validate/score` rejects absent/mismatched versions, changed/missing/reordered inputs, nonfinite measurements, a different model version, duplicate selection, and non-held-out IDs.

Commands from the repository root (bound native threads when training):

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 .venv/bin/python -m scripts.train_model --prepared data/processed/library-v1 --output data/processed/models/cox-v1/model.json
.venv/bin/python -m scripts.import_model --bundle data/processed/models/cox-v1/model.json
.venv/bin/python -m scripts.score_model --bundle data/processed/models/cox-v1/model.json --features data/processed/library-v1/features.csv --output data/processed/models/cox-v1/held-out-scores.json
```

`score_model` scores the matching checksummed prepared CSV (all held-out by default, or repeated `--patient LUNG1-002`). It rejects a changed CSV rather than assigning the frozen measurement version to arbitrary inputs. Live serving instead accepts the actual newly extracted records with their explicit version. Neither scoring path fits or evaluates a model. Use `requirements.txt` plus `requirements-model.txt` for reproducible runtime packages; PyRadiomics remains pinned to its source commit. The measured environment is Python 3.14.7; Linux deployment must install and verify the recorded package versions, not change the feature-version label to bypass a mismatch.

## Runner, GraphQL, and browser

Private engine environment additionally requires `MODEL_BUNDLE=/absolute/path/model.json` and `OUTCOMES_CSV=/absolute/path/library-v1/outcomes.csv`; `RAW_DIR` remains the prepared `library-v1/raw`. `ENGINE_SECRET`/`ENGINE_URL` preserve the private engine boundary. Native numerical and ITK threads default to one per tool subprocess, with operator environment overrides. Next/Vercel proxies to the separately hosted runner; no job singleton was added to Next.

The runner records QC → masks → features → eligibility preparation → score. Private `/eligibility` and `/score` run in the existing cancellable subprocess ownership boundary and consume actual supplied feature records, never cached reference features. Eligibility validates without computing scores, names every processing/outcome exclusion, and reports separate `scoring_eligible`/`evaluation_eligible` identities. Until #9 adds approval, any exclusion ends explicitly before `/score` with `approval_required`; no remaining features gives `no_scoreable_patients`. A missing outcome never removes an otherwise usable feature row or its scoring eligibility. All earlier mask-overlay/feature bytes remain browser-retainable. Clean runs score every selected patient, including one-patient selections, then emit terminal completion.

`run.model` holds the metadata version captured at creation; `run.eligibility` holds the report; `stage_results.score` uses the usual `{patient_id,status,values,artifacts,errors}` patient contract. `values` includes `risk_score`, `model_version`, `feature_version`, `score_definition`. Audit `tool_result` events use `{stage:'score',patient}`. The Analysis score card and generic History renderer consume these actual values; reload does not rerun imaging.

`python -m scripts.import_model --bundle ...` writes only immutable `model_metadata` in PostgreSQL. It verifies exact catalog/held-out membership and partition checksum, and refuses replacing a different frozen model. A genuinely new deployed model needs separately versioned catalog deployment. The local real catalog remains exactly 82 held-out rows; API test fixtures now use their own PostgreSQL schemas and do not insert test patients into it.

GraphQL `/api/graphql` adds:

```graphql
{ modelMetadata { model_version feature_version feature_schema development_count held_out_count reference_count reference_median partition_sha256 score_definition } }
query Results($id: ID!) {
  runResults(id: $id) { id status patient_ids model_version scores { patient_id risk_score model_version feature_version score_definition } }
}
```

`runResults` forwards the request's existing `Authorization: Bearer <run secret>` to the external runner's bounded `/runs/:id/results` query; it exposes no run listing or secret. Run creation, controls, and bounded event/artifact replay retain their existing REST endpoints. No visitor result/event data is written to Postgres or durable server storage.

## Handoff to #8 / #9 / #15

- #8: load this exact bundle via `FrozenModel`, use `reference_scores`/`reference_median` for fixed percentiles/groups and the exact 82 held-out membership for evaluation. `evaluation.status` is deliberately `not_evaluated`; no held-out c-index, uncertainty interval, percentile UI, or KM result is fabricated here. Remove/update the score card's current “not yet evaluated” text when actual evaluation lands. Evaluation assets can be separately versioned against this model without mutating its coefficients/reference distribution.
- #9: replace the explicit pre-score failure with the approved disclosure/checkpoint gate, preserving its report, exact feature records/version, model version, selected patient accounting, cancellation checks, and browser-only persistence. `invoke_model_tool('score', run, rows)` is the scoring continuation. Missing outcomes permit scoring after approval; they affect evaluation only.
- #15: ship the immutable prepared images/outcomes and this bundle behind the external runner/private engine; import model metadata into the matching Postgres catalog. Keep Vercel frontend separate. Reproduce dependencies and exercise the live extraction compatibility check on the deployment platform. Generated model/data/visitor outputs remain ignored.

## Verification and actual measurements

Observed TDD red states included absent model/scoring-tool modules, the clean API run failing without configured frozen metadata, and the prepared-CSV CLI accepting modified measurements before its checksum gate. Tests use the approved public numerical/tool, application API, and browser seams. Synthetic fixture tests do not establish clinical performance.

- Complete Python regression: 39 passed before adding the final CSV-provenance CLI test; the final six numerical/model-tool tests pass after that addition. Existing dependency deprecation warnings remain.
- Production Next build and TypeScript pass. Official Chromium: **25 passed**, including 24 History/reconnect/cancellation/catalog regressions and the actual real-data scoring browser check. Command with services running: `PLAYWRIGHT_BROWSERS_PATH=/private/tmp/mini-nota-browsers WEB_URL=http://localhost:3070 npx playwright test tests/scoring.spec.ts tests/history.spec.ts tests/cancellation.spec.ts tests/reconnect.spec.ts tests/catalog.spec.ts --reporter=line` from `web/`.
- All **82 real held-out** prepared feature rows scored; every patient's batch score equals its one-patient score exactly. Verification took **0.038 seconds** and score range was **−0.2584507805 to 0.5467313061**. Receipt: ignored `data/processed/models/cox-v1/scoring-verification.json`; complete scores: `held-out-scores.json`. This proves scoring consistency, not accuracy.
- Real browser patient **LUNG1-002** completed the full live pipeline in **10.041 seconds**, produced risk score **0.31620669544422614**, retained three artifacts (overlay plus JSON/CSV features), verified authorized GraphQL values and rejected unauthenticated result access, then retained results across History/reload. Receipt `/private/tmp/mini-nota-implementation/ticket7-live-receipt.json`, visually inspected screenshot `ticket7-live-scoring.png`, isolated service/browser harness `verify-ticket7-live.py` in that same directory. Only owned test ports 3070/8070/8071 were used and stopped.

No held-out performance evaluation, accuracy claim, hosted deployment, raw-data commit, or visitor-server persistence is included.

## Integration verification

Merged into `codex/mini-nota-mvp` at `352f60e`. The integrated production build/TypeScript and all 25 browser checks passed, including real LUNG1-002 scoring (0.31620669544422614), authorized GraphQL results, three locally retained artifacts, and History reload. The real catalog still exactly matches all 82 frozen held-out IDs, and every batch score equals its individual score exactly.

Integration review found that the new asynchronous metadata lookup followed #12's final launch-nonce check, reopening concurrent retry duplication. A public API regression reproduced eight different secrets for one nonce. Metadata now loads before the final check, so publishing the run and launch receipt remains atomic within the event loop. The complete pre-fix Python suite passed 40 tests; all 15 API tests passed after the correction, including the additional concurrent-retry regression.
