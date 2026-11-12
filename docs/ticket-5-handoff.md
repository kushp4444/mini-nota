# Real radiomic features (#5)

The runner now invokes the private `/features` tool after QC and masks, only for successful mask patients. Patient-associated tool results arrive one at a time as `{stage:'features', patient}` and remain in `run.stage_results.features`. Earlier QC/mask results and overlay bytes remain available, including when extraction fails. This slice explicitly stops after features: frozen-model scoring, outcome joins and approval are not invoked or simulated.

`FeatureResults` accepts selected IDs plus generic feature/QC/mask patient results. Its horizontally and vertically scrollable table retains every selected patient, displaying named failures and upstream exclusions rather than dropping rows or substituting zero. Select a patient for all measurements and a CSV download. Raw JSON/CSV retain full numeric precision; the UI displays eight significant digits. History #10 retains these same structured events and artifact blobs and shows the saved stage values/downloads without rerunning.

## Feature contract and numerical behavior

`EngineWorkspace.run_stage('features', patient_ids)` is also the offline preparation boundary. It reconstructs the deterministic RTSTRUCT mask using the same verified CT grid as mask display; verified spacing, LPS origin and direction reach PyRadiomics. Existing `extract_one` and `extract_all` use the same configured extractor. No unit-spacing fallback or alternate feature pipeline was added.

Successful patients expose `feature_schema` (lexicographically ordered configured original-image feature names), `values` (ordered name → finite float), and artifacts. The current configuration produces 72 features. The schema is derived from configured feature classes and their supported nondeprecated names; an unexpected output schema fails explicitly. Do not infer schema from pandas unions or silently fill missing columns. The JSON artifact contains numeric values; CSV includes `patient_id` followed by ordered feature columns. Both include role, size, SHA-256 and relative descriptive path metadata. The private engine copies bytes into `data_base64` before workspace cleanup; no durable server storage or temporary download URL is needed.

Non-finite image inputs and zero-variance images with configured normalization fail as `invalid_feature_input`. Non-finite or meaningfully complex measurements fail as `invalid_feature_value` naming the feature. Numerical complex scalars sufficiently close to real under NumPy's strict default floating-point tolerance convert to real; imaginary components are not discarded unconditionally. Schema disagreement fails as `feature_schema_mismatch`. Failed patients return no partial measurement row or feature artifact, and subsequent patients continue. Geometry/segmentation errors retain their existing named codes.

PyRadiomics uses the committed normalization and 1 mm resampling settings. Radiomic `original_shape_VoxelVolume` measures the resampled support; it is not the native-mask volume displayed by the mask stage. LUNG1-001 returned 161640 mm³ after resampling versus the native verified mask's 162039.7568 mm³. This expected distinction should remain explicit in later model/data documentation.

## Full-library preparation handoff

Use the existing shared immutable raw library only after acquisition/inventory is verified. Call the offline stage boundary for the objectively eligible patients, preserving requested order and every patient disposition. QC failures do not enter masks; mask failures do not enter features. Copy success artifacts or structured rows before leaving the workspace. Record failed/excluded patients separately, check exact schema equality, and save the committed radiomics configuration plus dependency versions with the preparation manifest. Never build an inner-joined table that silently loses failures. `extract_all` is a lower-level convenience for already-validated in-memory rows and fails fast rather than providing batch patient accounting; library preparation should use `EngineWorkspace` for named partial failures.

This ticket did **not** measure the full library, define partition membership, train a model, or publish full-cohort outputs. Those remain #6 onward. Do not label the current three-patient development catalog as the held-out library.

## Executed verification

- Red → green at the approved offline engine/numerical interface, public application API, and browser seams. Synthetic DICOM fixtures are explicitly labeled, independently specify physical contours and known 324 mm³ feature volume, and test constant-image failure before a later success. Existing independently justified normalized-mean fixture remains passing.
- `python -m pytest tests/test_service.py tests/test_features.py tests/test_engine.py tests/test_masks_geometry.py -q`: **21 passed**. API tests use real PostgreSQL and a real private HTTP engine, verify per-patient errors/progression, retained earlier stages, ordered schema/numeric rows and CSV checksum after workspace cleanup. Remaining warnings are dependency deprecations.
- `npm run build --prefix web`: production build and TypeScript pass after merging #10.
- `PLAYWRIGHT_BROWSERS_PATH=/private/tmp/mini-nota-browsers WEB_URL=http://localhost:3050 npm run test:e2e --prefix web`: **13 passed**, including ten History tests and three real LUNG1-001 workflow tests. Test selection now waits for catalog arrival; no empty-selection hydration race. Feature workflow confirms table, patient details, CSV bytes and preserved mask overlay.
- Actual local LUNG1-001 extraction: **72 finite values, 4.625 seconds**, one warm sample, not a full-library timing claim. Screenshot visually verified at `/private/tmp/mini-nota-implementation/features-browser.png` (not committed).
- Isolated verification services: private engine 8051, runner 8050, Next 3050. Each worktree owns a real independent `node_modules` directory.
