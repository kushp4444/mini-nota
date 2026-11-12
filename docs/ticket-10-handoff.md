# Browser-local History (#10)

`web/lib/history.ts` owns IndexedDB database `mini-nota-history` version 1. A run record is written atomically with its ordered events, selected patient IDs, opaque run reference/secret, last received sequence, optional checkpoint, terminal reason, and local artifact Blobs. `saveRun` rejects on failed transactions; the UI never reports a successful save after that rejection. Runs are keyed by their server-issued ID, so a new active view does not overwrite old records.

`captureEvent` accepts the public event contract from #3/#4. Any stage name is retained. A `tool_result` can provide artifacts in `payload.artifacts` or `payload.patient.artifacts` with `role`, `media_type`, and `data_base64` (preferred), or an application-proxied same-origin `url`. Engine filesystem `path` alone is never a usable saved artifact. Transport fields are removed from the stored event; all other structured stage data and artifact metadata are kept. Blob capture failures become named missing-artifact entries, rather than invented image results. Raw masks remain private/ephemeral; the engine chooses which derived artifacts to send.

`web/components/History.tsx` exports the generic `SavedArtifactView` blob renderer and renders all terminal states (`completed`, `failed`, `canceled`), structured results for arbitrary stage names, blob-backed images/downloads, and missing/unfinished-stage explanations. The existing agent panel reads the selected saved event timeline. Opening History performs no run API calls and never reruns the engine. Clearing site data, private browsing, quota exhaustion, or unsupported/damaged records cannot provide account-based recovery; the interface explains this.

## Follow-on integration

- #4: consume only `stage === 'qc'` events as QC; mask payloads must not be added to the QC result array. History already handles `stage === 'masks'` and overlay PNGs generically.
- #12: `readRuns` returns nonterminal records as well as terminal History. They retain `id`, `secret`, `lastSequence`, selected IDs, all received events/results/blobs, and the latest `payload.checkpoint`. Implement reconnection/control/restore using these credentials; do not mistake a lost SSE connection for a terminal server failure. This slice only shows a truthful unfinished-run notice after reload and implements no reconnect/restore API.
- Later feature/survival slices: emit structured `tool_result` payloads with their stage and real values. Include byte artifacts before temporary workspace cleanup. History has no stage-specific API dependency and already retains these results without fabricating unexecuted stages.
- No new server visitor persistence or run-listing endpoint is introduced.

## Verification

Next production build and TypeScript checks pass. Actual baseline red: ran the original saved-results browser test against a pristine e067190 app on port 3011; it failed because “Saved in this browser” does not exist there. After merging e067190 and preserving MaskResults, the History suite passes **10 browser tests** (Chromium headless shell):

```bash
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/mini-nota-browsers WEB_URL=http://127.0.0.1:3010 npx playwright test tests/history.spec.ts --reporter=line
npx tsc --noEmit
npm run build
```

Tests cover completed/failed/canceled runs across reload and a new run, PNG Blobs, ordered audit timelines, actual unfinished-stage labels, temporary URL removal, unavailable IndexedDB, quota failure, missing artifact bytes, and generic feature/survival values plus a retained CSV download. Browser fixtures are explicitly synthetic public API responses for persistence behavior, not measured imaging output; they neither invoke the real engine nor change raw data. Browser and Next server processes used isolated ports and were stopped after verification. This ticket changes no server code or persistence schema: IndexedDB writes stay in the browser, and History generates no run API requests.
