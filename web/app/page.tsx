"use client";
import MaskResults, { type MaskPatientResult } from "../components/MaskResults";
import FeatureResults, { type FeaturePatientResult } from "../components/FeatureResults";
import { useEffect, useRef, useState } from "react";
import History from "../components/History";
import {
  Audit,
  SavedRun,
  captureEvent,
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
    [unfinished, setUnfinished] = useState<SavedRun>();
  const activeRun = useRef<SavedRun | undefined>(undefined);
  useEffect(() => {
    readRuns()
      .then((runs) => {
        setHistory(runs.filter((run) => terminal(run.status)));
        setUnfinished(runs.find((run) => !terminal(run.status)));
      })
      .catch((e) => setStorageError(storageMessage(e)));
  }, []);
  async function persist(run: SavedRun) {
    activeRun.current = run;
    setSaved(false);
    try {
      await saveRun(run);
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
        setSelection(r.data.patients.map((p: Patient) => p.id));
      })
      .catch(() =>
        setError("The patient catalog is unavailable. Please try again later."),
      );
  }, []);
  async function start() {
    if (
      !selection.length ||
      selection.some((id) => !catalog.some((p) => p.id === id))
    ) {
      setError("Select at least one available patient.");
      return;
    }
    setError("");
    setSaved(false);
    activeRun.current = undefined;
    setEvents([]);
    setResults([]);
    setMasks([]);
    setFeatures([]);
    setStatus("running");
    setView("Analysis");
    try {
      const created = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ patient_ids: selection }),
      });
      const run = await created.json();
      if (!created.ok) throw Error(run.detail || "Unable to start run");
      await persist(createSavedRun(run, selection));
      const response = await fetch(`/api/runs/${run.id}/events`, {
        headers: { Authorization: `Bearer ${run.secret}` },
      });
      if (!response.ok || !response.body)
        throw Error("Unable to connect to run");
      const reader = response.body.getReader(),
        decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let split;
        while ((split = buffer.indexOf("\n\n")) >= 0) {
          const block = buffer.slice(0, split);
          buffer = buffer.slice(split + 2);
          const line = block.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const event: Audit = JSON.parse(line.slice(6));
          setEvents((prev) =>
            prev.some((e) => e.id === event.id) ? prev : [...prev, event],
          );
          if (activeRun.current)
            await persist(await captureEvent(activeRun.current, event));
          if (event.kind === "tool_result" && event.payload.patient) {
            if (event.payload.stage === "qc")
              setResults((prev) => [...prev, event.payload.patient as Result]);
            if (event.payload.stage === "masks")
              setMasks((prev) => [...prev, event.payload.patient as MaskPatientResult]);
          }
          if (event.kind === "tool_result" && event.payload.stage === "features" && event.payload.patient)
            setFeatures((prev) => [...prev, event.payload.patient as FeaturePatientResult]);
          if (event.kind === "done")
            setStatus(event.payload.status || "completed");
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run unavailable");
      // A broken connection is not proof that server computation failed.
      const current = activeRun.current as SavedRun | undefined;
      setStatus(
        current && !terminal(current.status) ? "interrupted" : "failed",
      );
    }
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
            <i /> Public Lung1 · fixture library
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
              <span className="tag">DEVELOPMENT FIXTURE</span>
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
                <strong>QC → masks → features</strong>
              </div>
            </div>
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
            {view !== "History" && unfinished && (
              <div role="status" className="card recovery-note">
                An unfinished run ({unfinished.id}) was saved locally with{" "}
                {unfinished.events.length} audit events. Reconnection is not
                available in this slice. Closing this page did not cancel server
                work; results never received here may be lost.
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
                      Clearly labeled fixtures · not the final held-out library
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
                          <span className="fixture">Fixture</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="table-footer">
                  <span>{catalog.length} available patients</span>
                  <button
                    className="primary"
                    disabled={!selection.length || status === "running"}
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
                      {selection.length} patients · QC, masks and features
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
                        disabled={!selection.length || status === "running"}
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
