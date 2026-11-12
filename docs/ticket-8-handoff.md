# Fixed-reference interpretation and survival evaluation (#8)

The first held-out evaluation of frozen model `cox-v1-a8e2738d012902a6f717` is **Harrell c-index 0.6057961981925833 on all 82 reserved patients**: 73 observed events, 9 censored. There are **zero processing or outcome exclusions within this held-out partition**. Neither model coefficients, reference scores/median, model version, feature measurements, development decisions, nor partition were changed after seeing this result. No performance target was used.

`docs/held-out-evaluation-v1.json` is the separately versioned immutable evaluation asset, version **`held-out-v1-59301a6ba6104aea1954`**, bound to the exact bundle content hash, partition hash, prepared features and outcomes. It includes every evaluated patient ID, full observed-survival curves, units, actual counts, explicit empty exclusion lists, and uncertainty settings. The frozen model bundle's original `evaluation.status=not_evaluated` remains unchanged; the separate evaluation table is the deployed source of completed evaluation metadata.

The context is the objectively prepared public Lung1 library: 422 inventoried source patients, 8 pre-partition processing exclusions, 414 usable, 332 development, 82 held-out. The eight source exclusions remain outside the frozen partition: QC spacing/regular-grid failures for LUNG1-014/021/085/095/194/246, RTSTRUCT/reference validation failure for LUNG1-035, missing requested GTV-1 for LUNG1-128. See `docs/ticket-6-handoff.md` and the ignored preparation report for those objective source dispositions; they are not selectively removed test outcomes. All 422 source patients had valid outcome joins. Outcomes are recorded in **days**.

## Interpretation and methods

`FrozenModel.score` now adds `risk_percentile` and `risk_group` without altering its fitted numeric inputs or outputs. Percentile is the upper empirical rank: `100 × count(reference score <= patient score) / 332`; a tie includes all equal reference scores. Strictly above the saved development median is **higher model risk**; at or below is **lower model risk**. This reference and threshold never depend on selection. Scores, percentiles and groups are exactly identical in individual/batch/reversed-order scoring.

Concordance uses lifelines 0.30.3 Harrell concordance with **negative log-risk** as its survival-order input: higher risk predicts shorter observed survival, tied risks get half credit, and comparable/censored/tied-outcome pairs follow lifelines admissibility. One patient or no comparable pairs returns null with a reason. A valid feature row with missing, invalid, duplicate or explicitly unsupported-unit outcome remains scored but receives a named evaluation exclusion. Prepared and runtime outcome contracts use days; numeric legacy numerical fixtures without a unit use that same contract.

The full-cohort 95% uncertainty interval is **[0.5326564103414366, 0.6739709514124799]**. The method was pinned as 2,000 patient-level nonparametric resamples with replacement, NumPy `default_rng` PCG64 seed 1729, taking linear 2.5th/97.5th percentiles of estimable Harrell c-indices. All 2,000 samples were estimable, zero unestimable. Unestimable samples are explicitly counted and excluded; fewer than two estimable samples yields no interval. This interval conditions on the frozen fitted model and resamples this finite test cohort; it does **not** include model-development/training uncertainty or establish clinical validity. There was no interval-method search based on the result.

Kaplan–Meier uses recorded event/censoring times and fixed groups. The SVG uses horizontal-then-vertical steps from the lifelines event table, actual group/event counts, and a days axis. One populated group draws one curve and explains the unavailable comparison; no usable outcomes draws no curve. Curves are selected-cohort exploratory summaries and never assume separation. Concordance is an ordering statistic among comparable outcomes, not a percentage of patients correctly predicted. Neither score nor percentile predicts death probability, lifespan or a clinical category.

## Deployment and public contracts

Run from the checkout with its Python environment:

```bash
python -m scripts.evaluate_model --bundle /path/model.json --prepared /path/library-v1 --output docs/held-out-evaluation-v1.json
python -m scripts.import_evaluation --bundle /path/model.json --evaluation docs/held-out-evaluation-v1.json
```

Evaluation verifies prepared input checksums against the frozen bundle, scores the exact full reserved membership, and refuses overwriting a different evaluation asset. The import requires the matching catalog model, checks the evaluation version/content and bundle, and writes only the immutable `model_evaluation` table keyed by model version. It refuses replacing a different imported evaluation. It writes no visitor data and does not mutate `model_metadata` or the bundle. Import this separate asset into each deployed catalog after `import_model`; otherwise the UI explicitly reports the full evaluation unavailable. The local test imported only into isolated PostgreSQL schema `ticket8_verify`, never replaced the production catalog.

GraphQL `modelMetadata.evaluation` exposes the full static evaluation independently of a selected run, with typed counts, exclusions, uncertainty, curves and version. `RiskScore` adds `risk_percentile`/`risk_group`; authorized `runResults.evaluation` exposes selected-cohort evaluation. The actual model-tool score response includes `evaluation`; #9 preserves it in the run snapshot, authorized results, and a `tool_result` event with `stage:evaluation`. The run plan captures catalog model metadata, so browser History can prefer its saved baseline over the current catalog. Browser-local events retain curves and summaries; History renders them without running the engine. Earlier historical runs lacking that model snapshot fall back to current static metadata, while their selected score/evaluation events remain original.

## Verification and handoff

TDD red receipts included absent evaluation module, missing percentile in public scoring output, missing main evaluation UI, and unsupported outcome units being mislabeled as days. Public numerical checks cover direction, boundary/tie rules, no outcomes/no comparable pairs/one-patient cases, explicit exclusions, exact KM worked values, reproducible bootstrap with counted unestimable samples, and preserved scoring for missing outcomes. Existing model tests check exact per-patient equality across selection and order.

The real-data release browser check runs QC → masks → features → scoring for LUNG1-002 (risk score 0.31620669544422614, percentile 96.08433734939759, higher model risk), checks GraphQL percentile/group and exploratory evaluation, sees the fixed 0.606 / n=82 baseline before/after selection, verifies a one-patient curve and unavailable c-index, then reloads History and verifies the saved curve. Representative actual overlay and curve screenshot: `/private/tmp/mini-nota-implementation/ticket8-evaluation.png` (visually inspected); isolated harness: `verify-ticket8-live.py` in that directory, ports 3080/8080/8081, PostgreSQL schema `ticket8_verify`.

Verification results and final integration commit are reported by the implementing agent. No hosted deployment or clinical-validity claim is made by this ticket.

## Final merged verification

Merged integration tip `50c5f70` (#9 approval/checkpoint delivery) into this branch as `20d5431`. The merge keeps #9's private-API/worker propagation and re-disclosure behavior, both gate/evaluation CSS, and one scoring regression for the identical disclosure-race behavior. `run_model_tool(..., expected_eligibility=...)` reads outcomes once, compares the freshly joined scoring/evaluation identities and named evaluation exclusions to the disclosed report **before computing scores**, then computes exploratory evaluation from that same outcome snapshot. A changed outcome cohort raises `ModelError('Eligibility changed after disclosure')`; #9 re-prepares/discloses instead of silently scoring it. This replaces the temporary recursive second-outcome-read guard and closes the join race.

On the merged branch:

- `python -m pytest -q`: **52 passed**, 43 existing dependency deprecation warnings, 86.31 seconds. This includes numerical imaging/model/evaluation boundaries and real application API orchestration with isolated PostgreSQL schemas.
- `npm run build --prefix web`: production Next build and TypeScript **passed**.
- `PYTHONPATH=. <shared-python> /private/tmp/mini-nota-implementation/verify-ticket8-live.py tests/evaluation.spec.ts tests/scoring.spec.ts tests/approval.spec.ts tests/history.spec.ts tests/cancellation.spec.ts tests/reconnect.spec.ts tests/catalog.spec.ts`: **27 passed**, 40.5 seconds. The real one-patient run and authorized GraphQL checks passed; History retained both the frozen full baseline and selected curve after reload with all API requests explicitly blocked.
- Recomputed versioned evaluation against checksummed prepared inputs: identical version and all values; no overwrite or model mutation. All 82 score/percentile/group values exactly match their individual, batch and reversed-order computations (39 higher, 43 lower), 0.038 seconds.
- Original model file checksum remains **`c6ce07c581c99569644f294eed611c7018b131df6938ed1e62719fc05a8cb89b`**. Final `git diff --check` passes, current integration is an ancestor, and no raw/generated visitor data or dependency environments were committed.

The actual full-cohort KM plot was also rendered and visually inspected: `/private/tmp/mini-nota-implementation/ticket8-held-out-curves.png`. Lower group n=43/events=39; higher n=39/events=34. The natural late curve crossing is retained. This plot is a release inspection artifact; the product displays selected-cohort observed curves.

## Integration verification and actual catalog import

Integrated `78377f2` into `codex/mini-nota-mvp` at merge `8f20379`. Imported this immutable asset into the actual local PostgreSQL public catalog using `scripts.import_evaluation`; returned `held-out-v1-59301a6ba6104aea1954`. Verified public catalog still contains exactly the original 82 held-out patients and zero fixtures; original `model_metadata.evaluation.status` remains `not_evaluated`, with completed evaluation loaded separately from `model_evaluation`.

Focused integration checks passed: 7 numerical/scoring tests; production Next.js build and TypeScript; one real LUNG1-002 browser/API workflow against the public catalog on isolated ports 3180/8180/8181, including fixed full baseline, selected one-patient curve/unavailable concordance, authorized percentile result, and offline History reload. Visually inspected its actual overlay, score, baseline and curve screenshot. Recomputed the full checksummed evaluation into a temporary asset: identical committed asset, c-index 0.6057961981925833, 82 evaluated, 95% interval [0.5326564103414366, 0.6739709514124799], all 2,000 bootstrap samples estimable. Frozen model SHA-256 remains `c6ce07c581c99569644f294eed611c7018b131df6938ed1e62719fc05a8cb89b`. No integration fixes were necessary; no tracker closure or push performed.
