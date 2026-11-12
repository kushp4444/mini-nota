"use client";
import ApprovalGate from "../components/ApprovalGate";
import ScoreResults from "../components/ScoreResults";
import MaskResults, { type MaskPatientResult } from "../components/MaskResults";
import FeatureResults, { type FeaturePatientResult } from "../components/FeatureResults";
import { useEffect, useRef, useState } from "react";
import History from "../components/History";
import { recoverLaunch, StoppedLaunch } from "../lib/launch";
import { reconnectRun } from "../lib/reconnect";
import CancelRun from "../components/CancelRun";
import { browserRun, watchBrowserRun, reserveBrowserRun, attachBrowserRun, releaseBrowserRun, pendingLaunch, reclaimBrowserRun, type PendingLaunch } from "../lib/browser-run";
import {
  Audit,
  SavedRun,
  createSavedRun,
  readRuns,
  saveRun,
  storageMessage,
  terminal,
} from "../lib/history";
type Patient = { id: string; label: string; fixture: boolean };
type Result = {
  patient_id: string;
  status: string;
  values: Record<string, { passed: boolean; detail: string }>;
  errors: { message: string }[];
};
export default function Home() {
  const [view, setView] = useState("Patients"),
    [catalog, setCatalog] = useState<Patient[]>([]),
    [selection, setSelection] = useState<string[]>([]),
    [events, setEvents] = useState<Audit[]>([]),
    [results, setResults] = useState<Result[]>([]),
    [masks, setMasks] = useState<MaskPatientResult[]>([]),
    [features, setFeatures] = useState<FeaturePatientResult[]>([]),
    [status, setStatus] = useState("idle"),
    [error, setError] = useState(""),
    [history, setHistory] = useState<SavedRun[]>([]),
    [savedSelection, setSavedSelection] = useState<SavedRun>(),
    [storageError, setStorageError] = useState(""),
    [saved, setSaved] = useState(false),
    [unfinished, setUnfinished] = useState<SavedRun>(),
    [browserBusy, setBrowserBusy] = useState(false),
    [recoveringHistory, setRecoveringHistory] = useState(true),
    [launchPending, setLaunchPending] = useState<PendingLaunch>();
  const connection = useRef<AbortController | undefined>(undefined);
  const activeRun = useRef<SavedRun | undefined>(undefined);
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
          setUnfinished(pending);
          setSelection(pending.patientIds);
          setView("Analysis");
          void follow(pending);
        } else {
          const launch = pendingLaunch();
          if (launch) void launchAndFollow(launch);
        }
      })
      .catch((e) => setStorageError(storageMessage(e)))
      .finally(() => setRecoveringHistory(false));
    return () => connection.current?.abort();
  }, []);
  async function persist(run: SavedRun) {
    if (activeRun.current?.id === run.id && terminal(activeRun.current.status) && !terminal(run.status)) return;
    activeRun.current = run;
    if (terminal(run.status)) { releaseBrowserRun(run.id); if (run.launchNonce) releaseBrowserRun(run.launchNonce); }
    setSaved(false);
    try {
      await saveRun(run);
      if (run.launchNonce) attachBrowserRun(run.launchNonce, run.id);
      if (terminal(run.status)) releaseBrowserRun(run.id);
      setSaved(true);
      setStorageError("");
      if (terminal(run.status))
        setHistory((prev) => [run, ...prev.filter((r) => r.id !== run.id)]);
    } catch (e) {
      setStorageError(storageMessage(e));
    }
  }
  const displayedEvents =
    view === "History" ? savedSelection?.events || [] : events;
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
  async function displayRun(run: SavedRun) {
    setEvents(run.events);
    setStatus(run.status);
    setFeatures(run.events.filter(e => e.kind === "tool_result" && e.payload.stage === "features" && e.payload.patient).map(e => e.payload.patient));
    setResults(run.events.filter(e => e.kind === "tool_result" && e.payload.stage === "qc").map(e => e.payload.patient));
    const patients = structuredClone(run.events.filter(e => e.kind === "tool_result" && e.payload.stage === "masks").map(e => e.payload.patient));
    for (const patient of patients) {
      for (const artifact of patient.artifacts || []) {
        const savedArtifact = run.artifacts.find(a => a.patientId === patient.patient_id && a.role === artifact.role && a.blob);
        if (savedArtifact?.blob) artifact.data_base64 = await new Promise<string>(resolve => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(",")[1]);
          reader.readAsDataURL(savedArtifact.blob!);
        });
      }
    }
    setMasks(patients);
  }
  async function follow(run: SavedRun) {
    connection.current?.abort();
    const controller = new AbortController();
    connection.current = controller;
    activeRun.current = run;
    await reclaimBrowserRun(run.id);
    await displayRun(run);
    try {
      await reconnectRun(run, async next => {
        await persist(next);
        if (controller.signal.aborted) return;
        await displayRun(next);
        setUnfinished(terminal(next.status) ? undefined : next);
        if (next.reason && next.status === "failed") setError(next.reason);
      }, controller.signal);
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
    setEvents([]);
    setResults([]);
    setMasks([]);
    setFeatures([]);
    setStatus("running");
    setView("Analysis");
    await launchAndFollow({nonce:reservation,patientIds:selection});
  }
  async function launchAndFollow(launch: PendingLaunch) {
    setLaunchPending(launch);
    setView("Analysis");
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
      if (e instanceof StoppedLaunch) {
        releaseBrowserRun(launch.nonce);
        setLaunchPending(undefined);
        const failed = {...createSavedRun({id:`launch-${launch.nonce}`,secret:"",status:"failed"},launch.patientIds), reason:e.message};
        await persist(failed);
        setStatus("failed");
      } else setStatus("disconnected");
      setError(e instanceof Error ? e.message : "Launch recovery unavailable");
    }
  }

  async function approveCurrent() {
    const run = activeRun.current;
    if (!run || run.status !== "waiting_approval") return;
    const checkpoint = run.checkpoint as {disclosure_id:string;model_version:string};
    const response = await fetch(`/api/runs/${run.id}/approve`, {method:"POST",headers:{Authorization:`Bearer ${run.secret}`,"Content-Type":"application/json"},body:JSON.stringify({disclosure_id:checkpoint.disclosure_id,model_version:checkpoint.model_version})});
    if (!response.ok) throw Error(response.status === 409 ? "The disclosed cohort changed. Review the updated patient report before approving." : "Approval was not confirmed. Retry when the service is available.");
  }
  async function cancelCurrent() {
    const run = activeRun.current;
    if (!run || terminal(run.status)) return;
    const headers = { Authorization: `Bearer ${run.secret}` };
    const response = await fetch(`/api/runs/${run.id}/cancel`, { method: 'POST', headers });
    if (!response.ok) throw Error('Cancellation was not confirmed. Please retry; processing may still be active.');
    connection.current?.abort();
    await follow(activeRun.current || run);
  }
  return (
    <div className="shell">
      <aside className="nav">
        <div className="brand">
          <span className="mark">△</span>
          <div>
            Mini-Nota<small>IMAGING WORKSPACE</small>
          </div>
        </div>
        <div className="workspace">
          Lung1 demonstration <span>⌄</span>
        </div>
        <div className="nav-label">WORKSPACE</div>
        {[
          ["Patients", "▦"],
          ["Analysis", "▥"],
          ["History", "◷"],
        ].map(([name, icon]) => (
          <button
            key={name}
            className={view === name ? "active" : ""}
            onClick={() => setView(name)}
          >
            <span aria-hidden="true">{icon}</span>
            {name}
          </button>
        ))}
        <div className="nav-bottom">
          <span className="avatar">MN</span>
          <div>
            Public research data<small>DEMONSTRATION ONLY</small>
          </div>
        </div>
      </aside>
      <div className="content">
        <header>
          <span>▥</span> {view}
          <div className="header-right">
            <i /> Public Lung1 · {catalog.some((p) => p.fixture) ? "fixture library" : "held-out library"}
          </div>
        </header>
        <div className="disclaimer">
          Public de-identified Lung1 data · Demonstration only · Not a medical
          device or medical advice.
        </div>
        <main>
          <section className="center">
            <div className="page-title">
              <div>
                <div className="eyebrow">IMAGING ANALYSIS</div>
                <h1>
                  {view === "Patients"
                    ? "Patient library"
                    : view === "Analysis"
                      ? "Cohort analysis"
                      : "Run history"}
                </h1>
                <p>
                  {view === "Patients"
                    ? "Select a cohort to inspect scan quality, tumor masks and radiomic features."
                    : "An auditable view of your imaging workflow."}
                </p>
              </div>
              <span className="tag">{catalog.some((p) => p.fixture) ? "DEVELOPMENT FIXTURE" : "FROZEN HELD-OUT LIBRARY"}</span>
            </div>
            <div className="card overview">
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
                <strong>{selection.length} patients</strong>
              </div>
              <div>
                <small>Workflow</small>
                <strong>QC → masks → features → scoring</strong>
              </div>
            </div>
            {browserBusy && !activeRun.current && <p role="status">A run is already active or awaiting approval in this browser. Return to its tab to finish or cancel it.</p>}
            {activeRun.current && !terminal(activeRun.current.status) && <CancelRun onConfirm={cancelCurrent} />}
            {error && (
              <div role="alert" className="error">
                {error}
              </div>
            )}
            {storageError && (
              <div role="alert" className="error">
                {storageError}
              </div>
            )}
            {view !== "History" && launchPending && <div role="status" className="card recovery-note">
              Recovering a pending launch. The saved request identifies the same run; server work has not been canceled.
              {status === "disconnected" && <button onClick={() => launchAndFollow(pendingLaunch() || launchPending)}>Retry launch recovery</button>}
            </div>}
            {view !== "History" && unfinished && (
              <div role="status" className="card recovery-note">
                Reconnecting saved run ({unfinished.id}) from event {unfinished.lastSequence}.
                Closing this page does not cancel server work.
                {status === "disconnected" && <button onClick={() => follow(unfinished)}>Retry reconnection</button>}
              </div>
            )}
            {view !== "History" &&
              saved &&
              terminal(status) &&
              !storageError && (
                <p role="status" className="persistence-status">
                  Saved in this browser
                </p>
              )}
            {view !== "History" &&
              activeRun.current?.artifacts.some(
                (artifact) => artifact.error,
              ) && (
                <p role="alert" className="error">
                  Some artifacts could not be saved. Open History for the
                  available results and named missing-artifact reasons.
                </p>
              )}
            {view === "History" ? (
              <History
                runs={history}
                selected={savedSelection}
                onSelect={setSavedSelection}
              />
            ) : view === "Patients" ? (
              <div className="card">
                <div className="card-heading">
                  <div>
                    <h2>Patients</h2>
                    <p>
                      {catalog.some((p) => p.fixture)
                        ? "Clearly labeled fixtures · not the final held-out library"
                        : `${catalog.length} frozen held-out patients · excluded from model development`}
                    </p>
                  </div>
                  <span>{selection.length} selected</span>
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>
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
                      <th>Patient ID</th>
                      <th>Collection</th>
                      <th>Catalog context</th>
                    </tr>
                  </thead>
                  <tbody>
                    {catalog.map((p) => (
                      <tr key={p.id}>
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
                <div className="table-footer">
                  <span>{catalog.length} available patients</span>
                  <button
                    className="primary"
                    disabled={recoveringHistory || !selection.length || browserBusy || Boolean(activeRun.current && !terminal(activeRun.current.status))}
                    onClick={start}
                  >
                    Run analysis <span>→</span>
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="card run-summary">
                  <div className="run-icon">▥</div>
                  <div>
                    <small>Selected cohort</small>
                    <strong>
                      {selection.length} patients · QC, masks, features and scoring
                    </strong>
                  </div>
                  <span className={`status ${status}`}>
                    {status === "idle" ? "Ready to run" : status}
                  </span>
                </div>
                <div className="card results">
                  <div className="card-heading">
                    <div>
                      <h2>Scan quality</h2>
                      <p>Geometry, slice spacing, and anonymization</p>
                    </div>
                    <span>
                      {results.length} / {selection.length} checked
                    </span>
                  </div>
                  {!events.length ? (
                    <div className="empty">
                      <div className="empty-icon">▥</div>
                      <h2>
                        {status === "running"
                          ? "Checking your selected cohort"
                          : "Ready when you are"}
                      </h2>
                      <p>
                        {status === "running"
                          ? "Waiting for the first scan result."
                          : "Start a run to see real patient checks arrive here."}
                      </p>
                      <button
                        className="primary"
                        onClick={start}
                        disabled={recoveringHistory || !selection.length || browserBusy || Boolean(activeRun.current && !terminal(activeRun.current.status))}
                      >
                        Run analysis →
                      </button>
                    </div>
                  ) : (
                    <div className="patient-results">
                      {selection.map((id) => {
                        const result = results.find((r) => r.patient_id === id);
                        return (
                          <article className="patient-result" key={id}>
                            <div className="patient-heading">
                              <strong>{id}</strong>
                              <span
                                className={`status ${result?.status || "pending"}`}
                              >
                                {result?.status || "Pending"}
                              </span>
                            </div>
                            {result ? (
                              <>
                                <div className="checks">
                                  {[
                                    "geometry",
                                    "slice_spacing",
                                    "anonymized",
                                  ].map((check) => (
                                    <div key={check}>
                                      <small>{check.replace("_", " ")}</small>
                                      <strong
                                        className={
                                          result.values[check]?.passed
                                            ? "pass"
                                            : "fail"
                                        }
                                      >
                                        {result.values[check]
                                          ? result.values[check].passed
                                            ? "✓ Passed"
                                            : "! Flagged"
                                          : "Unavailable"}
                                      </strong>
                                      <p>{result.values[check]?.detail}</p>
                                    </div>
                                  ))}
                                </div>
                                {result.errors.map((e, i) => (
                                  <p className="error-text" key={i}>
                                    {e.message}
                                  </p>
                                ))}
                              </>
                            ) : (
                              <p className="muted">Waiting for scan checks…</p>
                            )}
                          </article>
                        );
                      })}
                    </div>
                  )}
                </div>
                <MaskResults selectedIds={selection} results={masks} qcResults={results} />
                <FeatureResults selectedIds={selection} results={features} qcResults={results} maskResults={masks} />
                {activeRun.current && <ApprovalGate run={activeRun.current} onApprove={approveCurrent} />}
                <ScoreResults selectedIds={selection} events={events} />
              </>
            )}
          </section>
          <aside className="agent card">
            <div className="agent-heading">
              <span className="agent-mark">✳</span>
              <div>
                <h2>Workflow agent</h2>
                <p>Transparent by design</p>
              </div>
              <span className="live-dot" />
            </div>
            <div className="agent-intro">
              A fixed plan. Real tools.
              <br />
              Every result, in order.
            </div>
            <div className="stage-list">
              <span className={status === "running" ? "stage-running" : ""}>
                01
              </span>
              <div>
                <strong>Quality control</strong>
                <small>Selected-patient scan checks</small>
              </div>
            </div>
            <div className="stage-list">
              <span>02</span>
              <div><strong>Tumor masks</strong><small>Aligned overlays and physical volumes</small></div>
            </div>
            <div className="stage-list"><span>03</span><div><strong>Radiomic features</strong><small>Real quantitative measurements</small></div></div>
            <div className="stage-list"><span>04</span><div><strong>Frozen model scoring</strong><small>Fixed development model · no live fitting</small></div></div>
            <div className="timeline">
              {displayedEvents.length ? (
                displayedEvents.map((e) => (
                  <div key={e.id} className={`event ${e.kind}`}>
                    <span className="event-dot" />
                    <div>
                      <small>
                        {e.sequence.toString().padStart(2, "0")} ·{" "}
                        {e.kind.replace("_", " ")}
                      </small>
                      <p>{e.message}</p>
                      {view === "History" && (
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
            <div className="agent-foot">
              Temporary execution · no server run history
            </div>
          </aside>
        </main>
        <footer>
          Mini-Nota{" "}
          <span>Research workflow demonstration · Independent project</span>
        </footer>
      </div>
    </div>
  );
}
