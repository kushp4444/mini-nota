"use client";
import type { Example } from "../../lib/examples";
import ApprovalGate from "../../components/ApprovalGate";
import BetaModelResults from "../../components/BetaModelResults";
import ScoreResults, { HeldOutBenchmark } from "../../components/ScoreResults";
import QCResults from "../../components/QCResults";
import MaskResults from "../../components/MaskResults";
import FeatureResults from "../../components/FeatureResults";
import usePatientResults from "../../components/usePatientResults";
import MissingArtifact, { type ArtifactRecovery } from "../../components/MissingArtifact";
import { useEffect, useRef, useState } from "react";
import History from "../../components/History";
import RunPicker, { type ExampleKind } from "../../components/RunPicker";
import { LaunchNotStarted, recoverLaunch, StoppedLaunch } from "../../lib/launch";
import { reconnectRun } from "../../lib/reconnect";
import CancelRun from "../../components/CancelRun";
import { browserRun, watchBrowserRun, reserveBrowserRun, attachBrowserRun, releaseBrowserRun, pendingLaunch, reclaimBrowserRun, type PendingLaunch } from "../../lib/browser-run";
import {
  SavedRun,
  createSavedRun,
  readRuns,
  recoverArtifact,
  retainArtifactBytes,
  saveRun,
  storageMessage,
  terminal,
} from "../../lib/history";
type View = "Patients" | "Analysis" | "View Runs";

type Patient = { id: string; label: string; fixture: boolean };
export default function Workspace({ showCompletedExample, examples }: {
  showCompletedExample: boolean;
  examples: Record<ExampleKind, Example>;
}) {
  const [view, setView] = useState<View>(showCompletedExample ? "View Runs" : "Patients"),
    [catalog, setCatalog] = useState<Patient[]>([]),
    [selection, setSelection] = useState<string[]>([]),
    [displayedRun, setDisplayedRun] = useState<SavedRun>(),
    [status, setStatus] = useState("idle"),
    [error, setError] = useState(""),
    [history, setHistory] = useState<SavedRun[]>([]),
    [savedRunId, setSavedRunId] = useState<string>(),
    [storageError, setStorageError] = useState(""),
    [saved, setSaved] = useState(false),
    [gateIdle, setGateIdle] = useState(false),
    [unfinished, setUnfinished] = useState<SavedRun>(),
    [browserBusy, setBrowserBusy] = useState(false),
    [recoveringHistory, setRecoveringHistory] = useState(true),
    [launchPending, setLaunchPending] = useState<PendingLaunch>();
  const [exampleKind, setExampleKind] = useState<ExampleKind>("success");
  const viewingRuns = view === "View Runs";
  const example = viewingRuns && !savedRunId ? examples[exampleKind] : undefined;
  const savedSelection = viewingRuns ? history.find(run => run.id === savedRunId) : undefined;

  function selectView(name: View) {
    if (showCompletedExample && name !== "View Runs" && window.location.search) {
      window.history.replaceState(null, "", "/workspace");
    }
    setView(name);
  }

  function selectExample(kind: ExampleKind) {
    setSavedRunId(undefined);
    setExampleKind(kind);
  }
  const connection = useRef<AbortController | undefined>(undefined);
  const activeRun = useRef<SavedRun | undefined>(undefined);
  const persistedRun = useRef<SavedRun | undefined>(undefined);
  const gateUpdates = useRef<BroadcastChannel | undefined>(undefined);
  useEffect(() => {
    const updates = new BroadcastChannel('mini-nota-gate-updates');
    gateUpdates.current = updates;
    updates.onmessage = ({data}) => {
      const run = activeRun.current;
      if (run?.status === 'waiting_approval' && data === run.id) void follow(run);
    };
    return () => {
      updates.close();
      gateUpdates.current = undefined;
    };
  }, []);
  useEffect(() => watchBrowserRun(() => {
    try { setBrowserBusy(Boolean(browserRun())); }
    catch { setBrowserBusy(true); setError('Browser storage is unavailable; runs cannot be safely coordinated across tabs.'); }
  }), []);
  useEffect(() => {
    readRuns()
      .then((runs) => {
        setHistory(runs.filter((run) => terminal(run.status)));
        const pending = runs.find((run) => !terminal(run.status));
        if (pending) {
          persistedRun.current = pending;
          setUnfinished(pending);
          setSelection(pending.patientIds);
          if (!showCompletedExample) setView("Analysis");
          void follow(pending);
        } else {
          const launch = pendingLaunch();
          if (launch) void launchAndFollow(launch, showCompletedExample);
        }
      })
      .catch((e) => setStorageError(storageMessage(e)))
      .finally(() => setRecoveringHistory(false));
    return () => connection.current?.abort();
  }, []);
  async function persist(run: SavedRun) {
    if (activeRun.current?.id === run.id && terminal(activeRun.current.status) && !terminal(run.status)) return false;
    run = retainArtifactBytes(run, activeRun.current);
    activeRun.current = run;
    if (terminal(run.status)) { releaseBrowserRun(run.id); if (run.launchNonce) releaseBrowserRun(run.launchNonce); }
    setSaved(false);
    try {
      const stored = await saveRun(run);
      // A recovery may finish while this snapshot is being written.
      if (activeRun.current?.id === run.id)
        activeRun.current = retainArtifactBytes(activeRun.current, stored);
      persistedRun.current = stored;
      if (run.launchNonce) attachBrowserRun(run.launchNonce, run.id);
      if (terminal(run.status)) releaseBrowserRun(run.id);
      setSaved(true);
      setStorageError("");
      if (terminal(run.status))
        setHistory((prev) => [stored, ...prev.filter((r) => r.id !== run.id)]);
      return true;
    } catch (e) {
      setStorageError(storageMessage(e));
      return false;
    }
  }
  const events = displayedRun?.events ?? [];
  const { qc: results, masks, features } = usePatientResults(displayedRun);
  const analysisIds = displayedRun?.patientIds ?? launchPending?.patientIds ?? selection;
  const analysisEmpty = view === "Analysis" && status === "idle" && !displayedRun && !launchPending && !unfinished;
  const displayedEvents =
    viewingRuns ? (example ?? savedSelection)?.events ?? [] : events;
  useEffect(() => {
    fetch("/api/graphql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "{ patients { id label fixture } }" }),
    })
      .then((r) => r.json())
      .then((r) => {
        if (r.errors) throw Error("Catalog unavailable");
        setCatalog(r.data.patients);
        if (!activeRun.current && !browserRun()) setSelection(r.data.patients.map((p: Patient) => p.id));
      })
      .catch(() =>
        setError("The patient catalog is unavailable. Please try again later."),
      );
  }, []);
  const retryArtifact: ArtifactRecovery = async (run, artifact) => {
    const recovered = await recoverArtifact(run, artifact);
    const latest = activeRun.current?.id === run.id ? activeRun.current : run;
    const updated = {...latest, artifacts: latest.artifacts.map(item =>
      item.id === recovered.id && !item.blob ? recovered : item)};
    let stored: SavedRun;
    try {
      stored = await saveRun(updated);
      setStorageError("");
    } catch (failure) {
      setStorageError(storageMessage(failure));
      throw Error("Downloaded bytes could not be saved. Retry when browser storage is available.");
    }
    if (activeRun.current?.id === run.id) {
      activeRun.current = retainArtifactBytes(activeRun.current, stored);
      setDisplayedRun(activeRun.current);
    }
    if (terminal(stored.status)) {
      setHistory(previous => previous.map(item => item.id === stored.id ? stored : item));
    }
  };

  function displayRun(run: SavedRun) {
    setDisplayedRun(run);
    setStatus(run.status);
  }

  async function follow(run: SavedRun) {
    run = retainArtifactBytes(run, activeRun.current);
    connection.current?.abort();
    const controller = new AbortController();
    connection.current = controller;
    setGateIdle(false);
    setError("");
    activeRun.current = run;
    try {
      await reclaimBrowserRun(run.id);
      if (controller.signal.aborted) return;
      displayRun(run);
      const outcome = await reconnectRun(run, persistedRun.current?.id === run.id && persistedRun.current.lastSequence === run.lastSequence, async next => {
        const stored = await persist(next);
        if (controller.signal.aborted) return stored;
        const current = activeRun.current?.id === next.id ? activeRun.current : next;
        displayRun(current);
        setUnfinished(terminal(current.status) ? undefined : current);
        if (next.reason && next.status === "failed") setError(next.reason);
        return stored;
      }, controller.signal);
      if (!controller.signal.aborted && outcome === 'waiting_approval') {
        setSaved(true);
        setGateIdle(true);
      }
    } catch (e) {
      if (controller.signal.aborted) return;
      setError((e instanceof Error ? e.message : "Connection unavailable") + ". Server work has not been canceled. Retry reconnection to collect available results.");
      setUnfinished(activeRun.current);
      setStatus("disconnected");
    }
  }
  async function start() {
    if (recoveringHistory || (activeRun.current && !terminal(activeRun.current.status))) return;
    if (
      !selection.length ||
      selection.some((id) => !catalog.some((p) => p.id === id))
    ) {
      setError("Select at least one available patient.");
      return;
    }
    let reservation: string;
    try { reservation = await reserveBrowserRun(selection); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to coordinate runs in this browser.'); return; }
    setError("");
    setSaved(false);
    activeRun.current = undefined;
    setDisplayedRun(undefined);
    setStatus("running");
    setView("Analysis");
    await launchAndFollow({nonce:reservation,patientIds:selection});
  }
  async function launchAndFollow(launch: PendingLaunch, keepCurrentView = false) {
    setLaunchPending(launch);
    if (!keepCurrentView) setView("Analysis");
    setSelection(launch.patientIds);
    setStatus("connecting");
    setError("");
    try {
      const run = await recoverLaunch(pendingLaunch() || launch);
      const savedRun = {...createSavedRun({...run, status:"running"}, launch.patientIds), launchNonce:launch.nonce};
      await persist(savedRun);
      setLaunchPending(undefined);
      await follow(savedRun);
    } catch (e) {
      if (e instanceof LaunchNotStarted) {
        releaseBrowserRun(launch.nonce);
        setLaunchPending(undefined);
        setStatus("idle");
        if (!keepCurrentView) setView("Patients");
      } else if (e instanceof StoppedLaunch) {
        releaseBrowserRun(launch.nonce);
        setLaunchPending(undefined);
        const failed = {...createSavedRun({id:`launch-${launch.nonce}`,secret:"",status:"failed"},launch.patientIds), reason:e.message};
        await persist(failed);
        displayRun(failed);
      } else setStatus("disconnected");
      setError(e instanceof Error ? e.message : "Launch recovery unavailable");
    }
  }

  function refreshAfterControl(run: SavedRun) {
    gateUpdates.current?.postMessage(run.id);
    const current = activeRun.current;
    if (current?.id === run.id && !terminal(current.status)) void follow(current);
  }

  async function approveCurrent() {
    const run = activeRun.current;
    if (!run || run.status !== "waiting_approval") return;
    const checkpoint = run.checkpoint as {disclosure_id:string;model_version:string};
    const response = await fetch(`/api/runs/${run.id}/approve`, {method:"POST",headers:{Authorization:`Bearer ${run.secret}`,"Content-Type":"application/json"},body:JSON.stringify({disclosure_id:checkpoint.disclosure_id,model_version:checkpoint.model_version})});
    refreshAfterControl(run);
    if (!response.ok) throw Error(response.status === 409 ? "The disclosed cohort changed. Review the updated patient report before approving." : "Approval was not confirmed. Retry when the service is available.");
  }
  async function cancelCurrent() {
    const run = activeRun.current;
    if (!run || terminal(run.status)) return;
    const headers = { Authorization: `Bearer ${run.secret}` };
    const response = await fetch(`/api/runs/${run.id}/cancel`, { method: 'POST', headers });
    refreshAfterControl(run);
    if (!response.ok) throw Error('Cancellation was not confirmed. Please retry; processing may still be active.');
  }
  return (
    <div className={viewingRuns ? "shell run-report-layout" : "shell"}>
      <aside className="nav" aria-label="Analysis navigation">
        <div className="brand">
          <div>
            <a className="home-link" href="/">Mini-Nota</a>
            <small>Cohort imaging</small>
          </div>
        </div>
        <div className="workspace">
          Lung1 demonstration
        </div>
        <nav aria-label="Main navigation">
          {(["Patients", "Analysis", "View Runs"] as const).map((name) => (
            <button
              key={name}
              className={view === name ? "active" : ""}
              aria-current={view === name ? "page" : undefined}
              onClick={() => selectView(name)}
            >
              {name}
            </button>
          ))}
        </nav>
        <div className="nav-bottom">
          <div>
            Public research data<small>Demonstration only</small>
          </div>
        </div>
      </aside>
      <div className="content">
        {!viewingRuns && <header>
          <span>{view}</span>
          <div className="header-right">
            Public Lung1 · {catalog.some((p) => p.fixture) ? "fixture library" : "held-out library"}
          </div>
        </header>}
        {!viewingRuns && <div className="disclaimer">
          Public de-identified Lung1 data · Demonstration only · Not a medical
          device or medical advice.
        </div>}
        <main id="main-content">
          <section className="center" aria-labelledby={viewingRuns ? ((example ?? savedSelection) ? "report-heading" : "run-history-heading") : "page-heading"}>
            {!viewingRuns && <div className="page-title workspace-title">
              <h1 id="page-heading">{view === "Patients" ? "Patient library" : "Cohort analysis"}</h1>
            </div>}
            {!viewingRuns && !analysisEmpty && <div className="card overview">
              <div>
                <small>Collection</small>
                <strong>NSCLC Radiomics / Lung1</strong>
              </div>
              <div>
                <small>Available patients</small>
                <strong>{catalog.length}</strong>
              </div>
              <div>
                <small>Selected cohort</small>
                <strong>{(view === "Analysis" ? analysisIds : selection).length} patients</strong>
              </div>
              <div>
                <small>Workflow</small>
                <strong>QC → masks → features → scoring</strong>
              </div>
            </div>
            }
            {browserBusy && !activeRun.current && <p role="status">A run is already active or awaiting approval in this browser. Return to its tab to finish or cancel it.</p>}
            {activeRun.current && !terminal(activeRun.current.status) && <CancelRun onConfirm={cancelCurrent} />}
            {error && !viewingRuns && (
              <div role="alert" className="error">
                {error}
              </div>
            )}
            {storageError && (
              <div role="alert" className="error">
                {storageError}
              </div>
            )}
            {!viewingRuns && launchPending && <div role="status" className="card recovery-note">
              Recovering a pending launch. The saved request identifies the same run; server work has not been canceled.
              {status === "disconnected" && <button onClick={() => launchAndFollow(pendingLaunch() || launchPending)}>Retry launch recovery</button>}
            </div>}
            {!viewingRuns && unfinished && (
              <div role="status" className="card recovery-note">
                {gateIdle ? (
                  <button onClick={() => follow(unfinished)}>Refresh run status</button>
                ) : (
                  <>Reconnecting saved run ({unfinished.id}) from event {unfinished.lastSequence}. Closing this page does not cancel server work.</>
                )}
                {status === "disconnected" && <button onClick={() => follow(unfinished)}>Retry reconnection</button>}
              </div>
            )}
            {!viewingRuns &&
              saved &&
              (terminal(status) || status === "waiting_approval") &&
              !storageError && (
                <p role="status" className="persistence-status">
                  {status === "waiting_approval" ? "Approval gate saved in this browser" : "Saved in this browser"}
                </p>
              )}
            {view === "Analysis" && displayedRun?.artifacts.filter(artifact => !artifact.blob).map(artifact =>
              <MissingArtifact key={artifact.id} run={displayedRun} artifact={artifact} onRecover={retryArtifact} />
            )}
            {viewingRuns ? (
              <>
                <RunPicker
                  exampleKind={exampleKind}
                  savedRunId={savedRunId}
                  history={history}
                  recovering={recoveringHistory}
                  onSelectExample={selectExample}
                  onSelectRun={setSavedRunId}
                />
                <History
                  selected={example ?? savedSelection}
                  title={example ? (example.example.faults.length ? "Failure example" : "Completed example") : undefined}
                  subtitle={example ? (example.example.faults.length ? "Recorded exclusions." : "Tumor masks and 72 radiomic features per patient.") : undefined}
                  faults={example?.example.faults}
                  exampleFiles={example?.example.files}
                  onRecover={retryArtifact}
                />
              </>
            ) : view === "Patients" ? (
              <div className="card">
                <div className="card-heading patient-catalog-heading">
                  <div>
                    <h2>Patients</h2>
                    <p>
                      {catalog.some((p) => p.fixture)
                        ? "Clearly labeled fixtures · not the final held-out library"
                        : `${catalog.length} frozen held-out patients · excluded from model development`}
                    </p>
                    <p>Each selected patient gets scan checks, a tumor mask, and 72 radiomic features if processing succeeds. The beta survival model uses those features to score eligible patients.</p>
                  </div>
                </div>
                <div className="table-footer">
                  <span role="status">{selection.length} of {catalog.length} patients selected</span>
                  <button
                    className="primary"
                    disabled={recoveringHistory || !selection.length || browserBusy || Boolean(activeRun.current && !terminal(activeRun.current.status))}
                    onClick={start}
                  >
                    Run analysis
                  </button>
                </div>
                <div className="catalog-scroll" tabIndex={0} role="region" aria-label="Held-out patient selection">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">
                        <input
                          aria-label="Select all patients"
                          type="checkbox"
                          checked={
                            catalog.length > 0 &&
                            selection.length === catalog.length
                          }
                          onChange={(e) =>
                            setSelection(
                              e.target.checked ? catalog.map((p) => p.id) : [],
                            )
                          }
                        />
                      </th>
                      <th scope="col">Patient ID</th>
                      <th scope="col">Collection</th>
                      <th scope="col">Catalog context</th>
                    </tr>
                  </thead>
                  <tbody>
                    {catalog.map((p) => (
                      <tr key={p.id} className={selection.includes(p.id) ? "selected" : undefined}>
                        <td>
                          <input
                            aria-label={`Select ${p.id}`}
                            type="checkbox"
                            checked={selection.includes(p.id)}
                            onChange={(e) =>
                              setSelection((prev) =>
                                e.target.checked
                                  ? [...prev, p.id]
                                  : prev.filter((x) => x !== p.id),
                              )
                            }
                          />
                        </td>
                        <td>
                          <strong>{p.id}</strong>
                        </td>
                        <td>Public Lung1</td>
                        <td>
                          <span className="fixture">{p.fixture ? "Fixture" : "Held-out"}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>

              </div>
            ) : analysisEmpty ? (
              <>
                {recoveringHistory ? <p role="status">Checking for a saved run…</p> : !browserBusy && (
                  <section className="card stage-empty" aria-labelledby="analysis-empty-heading">
                    <h2 id="analysis-empty-heading">Start an analysis</h2>
                    <p>Choose patients and start a run. You can follow its progress here in real time.</p>
                    <button className="primary" onClick={() => selectView("Patients")}>Go to Patients</button>
                  </section>
                )}
                <BetaModelResults><HeldOutBenchmark events={events} /></BetaModelResults>
              </>
            ) : (
              <>
                <div className="card run-summary">
                  <div>
                    <small>Selected cohort</small>
                    <strong>
                      {analysisIds.length} patients · QC, masks, features and scoring
                    </strong>
                  </div>
                  <span className={`status ${status}`}>
                    {status === "idle" ? "Ready to run" : status}
                  </span>
                </div>
                {activeRun.current && <ApprovalGate run={activeRun.current} onApprove={approveCurrent} />}
                <QCResults selectedIds={analysisIds} results={results} ended={terminal(status)} />
                <MaskResults selectedIds={analysisIds} results={masks} qcResults={results} ended={terminal(status)} />
                <FeatureResults selectedIds={analysisIds} results={features} qcResults={results} maskResults={masks} ended={terminal(status)} />
                <BetaModelResults>
                  <ScoreResults selectedIds={analysisIds} events={events} showBenchmark={false} />
                  <HeldOutBenchmark events={events} />
                </BetaModelResults>
              </>
            )}
          </section>
          <aside id="record" className="agent card" aria-labelledby="agent-heading">
            <div className="agent-heading">
              <div>
                <h2 id="agent-heading">{viewingRuns ? "Run record" : "Agent panel"}</h2>
              </div>
            </div>
            {displayedEvents.some(event => event.kind === "tool_result" && event.payload.stage) &&
              <details className="completed-stages-disclosure">
                <summary>Completed stages</summary>
                <ul className="completed-stages" role="list">
                  {[
                    ["qc", "Scan checks passed"],
                    ["masks", "Tumor masks created"],
                    ["features", "Tumor measurements extracted"],
                    ["score", "Patients scored"],
                    ["evaluation", "Follow-up compared"],
                  ].filter(([stage]) => displayedEvents.some(event => {
                    if (event.kind !== "tool_result" || event.payload.stage !== stage) return false;
                    return stage === "evaluation" ? event.payload.evaluation?.c_index != null
                      : event.payload.patient?.status === "success";
                  })).map(([stage, label]) => <li key={stage}><span className="stage-check" aria-hidden="true">✓</span>{label}</li>)}
                </ul>
              </details>}
            <details key={view} open={view === "Analysis" || view === "Patients"}>
              <summary>Run events</summary>
            <div className="timeline" role="region" aria-label="Run events">
              {displayedEvents.length ? (
                displayedEvents.map((e) => (
                  <div key={e.id} className={`event ${e.kind}`}>
                    <span className="event-dot" aria-hidden="true" />
                    <div>
                      <small>
                        {e.sequence.toString().padStart(2, "0")} ·{" "}
                        {e.kind.replace("_", " ")}
                      </small>
                      <p>{e.message}</p>
                      {viewingRuns && savedSelection && (
                        <small>{new Date(e.timestamp).toLocaleString()}</small>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <p className="muted">
                  Your run’s plan, tool calls, and decisions will appear here.
                </p>
              )}
            </div>
            </details>
            {!example && <div className="agent-foot">
              Private run access · browser-local History
            </div>}
          </aside>
        </main>
        <footer>
          {viewingRuns ? <><span>Public de-identified Lung1 data</span><p>Demonstration only. Not a medical device or medical advice.</p></> : <>Mini-Nota{" "}
          <span>Research workflow demonstration · Independent project</span></>}
        </footer>
      </div>
    </div>
  );
}
