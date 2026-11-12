# Full-collection preparation and frozen catalog (#6)

`python -m scripts.prepare_library --raw-dir /path/data/raw --output-dir /path/data/processed/library-v1 --workers 4` inventories the installed IDC NSCLC-Radiomics manifest (422 patients, 422 CT series and 422 RTSTRUCT series). It makes no network requests. All expected source instance counts must be complete before processing starts; unfinished acquisition aborts, rather than producing false patient exclusions. Acquisition's size synchronization receipt is separate from preparation's content/geometry validation.

The original IDC directory remains the immutable source. Preparation hardlinks the deterministic single CT and RTSTRUCT into `raw/<patient>/ct` and `raw/<patient>/rtstruct.dcm`. Hardlinks avoid another 27 GB copy; all consumers must treat both paths as read-only. Never edit either link or original scan. Additional CT/RTSTRUCT alternatives are rejected as ambiguous rather than selected by filesystem order. All headers must match the manifest patient, modality and series, with unique SOP instances; unexpected patient names/birthdates alarm. Only the exact verified public Lung1 pseudonym allowance is permitted.

The public `prepare_collection` boundary runs the same `EngineWorkspace` QC → masks → features pipeline as live execution. It keeps each requested patient and each error. It requires verified CT geometry, matching RTSTRUCT references/frame, unique `GTV-1`, supported in-plane contours, nonempty masks and 72 finite configured radiomic features. Native volume, selected middle tumor slice and overlay use the verified native grid; resampled radiomic shape volume is separately measured. There is no learned full-cohort filtering, scaling, model training or score-based exclusion. Four processes each handle at most one patient, with ITK/BLAS/OpenMP thread counts bounded to one.

Outcomes use an exact patient join, duplicate-row checks, matching identifier columns, finite positive duration in days and event encoding 0/1. Invalid/missing outcomes are explicitly named and do not prevent scoring when imaging features are usable. Clinical records with no source patient are separately listed.

The partition is fixed only after objective eligibility, before any model fitting: SHA-256 ordering of `seed:patient_id` within observed-event, censoring and missing-outcome strata, seed 42, nearest-integer 20% allocation (both partitions represented for strata with at least two patients). No alternate seeds or held-out results are searched. Duplicate patient IDs abort. IDs and saved configuration are deterministic and disjoint.

## Immutable preparation outputs

Local version: `/Users/kushpatel/Projects/mini-nota/data/processed/library-v1` (ignored; never visitor storage).

- `source_manifest.json`: complete expected series/files; each patient's `sources` additionally records every source SOP, size and SHA-256.
- `provenance.json`: source identity/manifest hashes, clinical hash, exact radiomics configuration/hash, dependency versions, engine source hashes, objective policies, worker count and seed.
- `patients/<id>.json`: complete disposition and stage values/artifacts, with safe named errors. Same-input checkpoints resume interrupted offline preparation; changed input/configuration requires a new versioned directory.
- `report.json`: every inventoried patient, actual scoring/evaluation counts, clinical-only identities and all exclusions.
- `partition.json`: exact sorted `development`/`held_out` IDs, seed, fraction, method and observed-event stratum counts.
- `features.csv`: `patient_id` and all 72 ordered finite feature columns, only objectively scoreable patients. No imputation or filtering.
- `feature_schema.json`: exact ordered schema for model compatibility.
- `outcomes.csv`: `patient_id,duration,event,time_unit`, valid outcomes, including records for patients failing image processing. Modeling must explicitly select its intended patient partition.
- `catalog.json`: checksummed partition reference and exact real held-out public catalog.
- `artifacts/<patient>/`: measured PNG overlay and JSON/CSV features. Full working NPY masks remain temporary and are cleaned by the engine.

Model development (#7) must train only on `partition.development`, fit all learned preprocessing inside training folds and preserve the frozen membership. It must not silently reinterpret an exclusion or add development IDs to the catalog. Live private engine `RAW_DIR` points to this version's `raw` hardlinks.

## Catalog

`python -m scripts.seed_catalog --prepared /path/data/processed/library-v1` validates partition disjointness, unique membership, exact held-out catalog IDs, real-data flags and the partition SHA-256 before a transaction replaces catalog rows. It saves immutable catalog metadata/counts in PostgreSQL; it creates no visitor rows. Reimport is idempotent. The application and GraphQL retain their read-only catalog access, and run creation accepts only its IDs; a manually submitted development ID receives 422. `--fixtures` is explicit and refuses to seed over a frozen catalog. Tests use a separate temporary PostgreSQL schema, never delete or replace the real held-out rows.

The Patients view reads actual catalog count, defaults to all available IDs and labels real held-out rows separately from explicit fixtures. The browser never receives source paths or development identities from the catalog.

An existing frozen catalog refuses a different valid split as well as corrupted membership. A deliberately new library/model partition therefore requires a separately versioned database/catalog deployment, rather than silently changing patients under an active frozen model.

## Measured full-data release verification (2026-11-11)

The actual full run inventoried **422 patients** and **844 series**, with **414 scoring-eligible and evaluation-eligible patients**, **8 processing exclusions**, and **0 evaluation exclusions among usable patients**. Every one of the 422 clinical records had a valid unique outcome join. All 414 successful patients produced the same 72-feature schema with finite values. The frozen partition contains **332 development** (294 observed events, 38 censored) and **82 held-out** (73 observed events, 9 censored) patients. Exact reviewable public membership is committed in `docs/library-v1-partition.json`; SHA-256: `19e041a983bf105e890bd8c909b6ff3782b26336ddd5ac1e20562de71ebdf799`.

All exclusions are objective and retained in the full report:

| Patient(s) | Stage | Reason |
| --- | --- | --- |
| LUNG1-014, LUNG1-021, LUNG1-085, LUNG1-095, LUNG1-194, LUNG1-246 | QC | Nonuniform or duplicate physical slice spacing; unsupported regular-grid geometry |
| LUNG1-035 | Masks | Invalid RTSTRUCT / reference validation failure |
| LUNG1-128 | Masks | Requested GTV-1 tumor ROI absent |

Full four-worker preparation took **590.88 seconds** (about 9 minutes 51 seconds), including source hashing and actual QC/mask/feature measurements. A separate read-only pass rehashed **51,652 source DICOM instances / 27,538,432,270 bytes**, confirmed globally unique SOP identities, checked retained artifact sizes/SHA-256, all finite feature rows, complete patient accounting and disjoint/exhaustive membership: **passed in 41.67 seconds**. This verifies content against the prepared provenance and the completed IDC size synchronization, not an unpublished provider checksum. The acquisition receipt is `/private/tmp/mini-nota-implementation/resume-acquisition-result.json`; independent verification receipt is `/private/tmp/mini-nota-implementation/verify-prepared-library.json`.

Repeating the same preparation command returned identical persisted counts/membership without recomputing imaging. The real **82-patient held-out catalog is imported into the local PostgreSQL database**. A browser against the real GraphQL/PostgreSQL catalog verified exact held-out IDs, all selected by default, checkbox changes, no fixture rows and **422 rejection of a manually submitted development ID**. Screenshot: `/private/tmp/mini-nota-implementation/heldout-catalog-browser.png`. Real overlays LUNG1-100 and LUNG1-300 were visually inspected and align with their tumors.

After merging cancellation integration `ea652ed`, the public preparation/catalog/API and existing imaging/service suites passed **28 tests** using an isolated PostgreSQL schema and actual HTTP engine. Next production build/TypeScript passed. A focused browser regression exposed the remaining stale development-fixture badge before its correction; the resulting real catalog is labeled as the frozen held-out library.

No model training, tuning, held-out performance claim, raw-data commit, or visitor persistence was performed. Model development receives the exact ignored outputs listed above; runtime engine configuration must use `/Users/kushpatel/Projects/mini-nota/data/processed/library-v1/raw` rather than the old first-30-patient raw layout.

Focused catalog browser regression: `PLAYWRIGHT_BROWSERS_PATH=/private/tmp/mini-nota-browsers WEB_URL=http://localhost:3060 npx playwright test tests/catalog.spec.ts --reporter=line`: **1 passed** after the observed red fixture-badge failure. The browser transport fixture is explicitly synthetic; the separate 82-patient browser verification above used real PostgreSQL/GraphQL catalog data.
