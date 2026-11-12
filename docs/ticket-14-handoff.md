# Immediately viewable curated executions (#14)

The Patients screen exposes **View completed example** and **View failure example** above the live catalog; Examples also has a navigation destination. Both load immutable product JSON directly, with real PNG/feature bytes. They work when the runner/catalog is unavailable and launch no computation, create no browser run reservation, and write no IndexedDB history. Visitor History remains separate and browser-only.

`web/lib/examples.ts` feeds actual exported events through the same `captureEvent` artifact-byte contract used by live runs, then passes the terminal `SavedRun` to the normal History renderer. The existing agent panel presents its ordered events. History now shares the live feature table/patient-detail component and renders recorded approval disclosure as a read-only patient table. There is no resumable example checkpoint or approval action. Eligibility decision reports display as completed reports rather than unfinished tool calls; scored runs no longer gain a misleading unused legacy survival-stage placeholder.

## Actual provenance and deliberately introduced faults

Both assets were produced by `scripts/curate_examples.py`, which starts isolated real runner/private-engine services and drives the public run API against the exact prepared imaging library and frozen model **cox-v1-a8e2738d012902a6f717**, with original fixed development reference and **held-out-v1-59301a6ba6104aea1954** evaluation metadata. No reference/precomputed feature rows substitute for live extraction. The script changes no catalog/model/evaluation table.

- `curated-success.json`: LUNG1-002 and LUNG1-009 pass actual QC, mask construction, feature extraction and scoring; 22 ordered events, 16.046 seconds from plan to completion. Their scores are 0.31620669544422614 and 0.06046055488595205. The selected two-patient c-index is actually 0.0; both patients occupy the higher fixed model-risk group and its single curve is labeled accordingly. This deliberately makes no favorable performance claim. Main evaluation remains the independently measured full 82-patient result (0.6057961981925833).
- `curated-failure.json`: a disposable library contains the same immutable held-out scans for 002/009, plus a **new synthetic malformed DICOM file** for LUNG1-015. A separate temporary outcomes CSV deliberately omits 002. Actual QC reports InvalidDicomError for 015; 002 remains scoreable but is explicitly excluded from selected evaluation. The actual gate discloses **2 scoring-eligible / 1 evaluation-eligible** patients; the script records anonymous approval through the public API and real frozen scoring completes. There are 28 events, 17.354 seconds, and the eligible patients' scores match the success example exactly. A one-patient exploratory evaluation is correctly unavailable. These are labeled fault fixtures, not actual faults in the live library or full held-out evaluation.

Source scans are only hardlinked into the temporary directory and never modified. The malformed file is newly created under its own patient directory; the outcome CSV is separately written. Temporary services/directories are removed after generation. Only derived curated product assets are committed, not raw scans or visitor runs.

The exporter drops secrets, launch capabilities, checkpoint bodies/signatures/tokens, disclosure control IDs, and transport paths/URLs recursively. It retains gate report/reasons and terminal audit decisions; public example artifacts cannot restore or control a visitor run.

Asset SHA-256:

- success (484185 bytes): `cc0519bc896ec7c56a76b405a409f2b29cbbe5994d1a2b830535ac09e2d4b060`
- failure (495353 bytes): `218d8f9b7010d1d5e6885f2ebd2ea8858f2e838d1b1e39378af1a367e054003e`

Reproduce from the repository with the matching PostgreSQL catalog/model/evaluation imported:

```bash
/Users/kushpatel/Projects/mini-nota/.venv/bin/python -m scripts.curate_examples \
  --prepared /Users/kushpatel/Projects/mini-nota/data/processed/library-v1 \
  --bundle /Users/kushpatel/Projects/mini-nota/data/processed/models/cox-v1/model.json
```

Default isolated ports are 8140/8141; override with `--runner-port`/`--engine-port`. A real stable operator signing key is required for deployed visitor restoration; this disposable generator uses its own non-deployed key. Timestamps reflect actual generation, so regenerating assets changes their hashes.

## Verification

TDD's initial browser test failed because the completed-example action was absent; after implementation it passed. The browser seams were pre-approved in shared implementation instructions.

- Official Chromium: **12 passed** (`examples.spec.ts history.spec.ts`, isolated port 3140). Covers immediate static access without run API requests, patient feature details, real overlay display/PNG signatures, standing disclaimer, ordered plan/gate/approval/scoring/terminal events, labeled faults, named differing eligibility, absence of actionable approval/control material, no active-browser reservation, and examples not entering visitor History. Existing History failure/cancellation/reload/storage/blob regressions remain green.
- `npx tsc --noEmit` and `npm run build -- --webpack` pass.
- Actual generation completed both API/engine runs, with the exact measured values above. It did not alter raw data or the live catalog.
- Visually inspected the full actual success example screenshot at `/private/tmp/mini-nota-implementation/ticket14-example.png`; overlay masks and evaluation/feature sections render. This is a local runtime receipt, not a committed product image.

Static example assets are allowed server-side product assets under ADR 0001. No server visitor persistence or hosted deployment is introduced. Deployment must ship `web/public/examples` with the frontend; viewing these assets needs no Python worker. Live computation continues to require the external runner/private engine and PostgreSQL.

## Integration receipt

Merged into `codex/mini-nota-mvp` at `8d57768`. Independent integration verification used the production frontend on isolated port 3154: `npx tsc --noEmit`, `npm run build -- --webpack`, and Chromium `examples.spec.ts history.spec.ts` all passed (12 browser tests). No integration source fixes were needed. Exported asset hashes match the provenance receipt above; the exporter and loader were inspected for capability stripping and reuse of `captureEvent`/the normal History renderer.

The public GraphQL endpoint returned the unchanged 82-patient catalog with every `fixture=false`, frozen model `cox-v1-a8e2738d012902a6f717`, and 82 evaluated patients at c-index 0.6057961981925833. The synthetic malformed scan and removed outcome remain confined to the labeled static example. The production success screen visibly preserves the actual selected c-index 0.000 and single model-risk group. Independent screenshots are `/private/tmp/mini-nota-implementation/ticket14-integrated-success.png` (visually inspected) and `/private/tmp/mini-nota-implementation/ticket14-integrated-failure.png`.
