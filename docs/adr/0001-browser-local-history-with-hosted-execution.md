# Browser-local history with hosted execution

The server-persistence restriction in this decision is superseded by [ADR 0003](0003-modal-compute-with-durable-results.md), following the user's Render/Neon/R2/Modal hosting decision. The browser History, anonymous run control, approval and cancellation requirements remain in force.

Mini-Nota is a hosted recruiting demo that visitors can use without installation or authentication. Run history and completed results are persisted in browser storage; there is no server-side persistence of runs, events, or generated artifacts, and no user sessions are tracked. This trades account-based recovery and cross-device history for a low-friction demo: if local history is lost, the visitor starts a new run.

The browser retains a per-run secret for reconnecting and approving, without identifying a user or session. Approval has no time limit. Each browser may have only one run in progress, and the user can cancel it; one visitor's unanswered approval must not block other visitors.

The server may use temporary working memory and temporary files while computing, with cleanup afterward. The browser saves the data needed to resume at an approval gate and sends it back if server state has been lost. Closing the browser does not stop computation, but results that never reached browser storage may be lost.

This supersedes the initial proposal to persist run state and audit events on the server. The patient library and pretrained model remain available on the server; Postgres holds the read-only patient catalog and model metadata. The restriction applies to visitor runs, generated results, and audit events.

Cancel requires explicit confirmation before stopping work. Every terminal run (completed, canceled, or failed) retains its status, audit timeline, and all available stage results in browser-local history. Canceled and failed runs include the termination reason, and stages without results are shown with their actual status rather than fabricated outputs.

Starting a new run clears only the active run's in-flight results view. It does not delete or overwrite any historical run's saved results. This clarifies the earlier replacement requirement: replacement applies to the active display, not the historical artifacts.
