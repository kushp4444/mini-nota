"use client";
import { useEffect, useState } from "react";
import FeatureResults from "./FeatureResults";
import ScoreResults from "./ScoreResults";
import { SavedArtifact, SavedRun, terminal } from "../lib/history";
export function SavedArtifactView({ artifact }: { artifact: SavedArtifact }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!artifact.blob) return;
    const objectUrl = URL.createObjectURL(artifact.blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [artifact.blob]);
  if (!artifact.blob || artifact.error)
    return (
      <p role="alert" className="error-text">
        Missing artifact: {artifact.role}.{" "}
        {artifact.error || "Saved bytes are unavailable."}
      </p>
    );
  return (
    <figure className="saved-artifact">
      {artifact.mediaType.startsWith("image/") && url ? (
        <img
          src={url}
          alt={`${artifact.patientId || artifact.stage} ${artifact.role}`}
        />
      ) : null}
      <figcaption>
        {artifact.role} · {artifact.blob.size} bytes · saved locally
      </figcaption>
      {url && (
        <a
          href={url}
          download={`${artifact.patientId || artifact.stage}-${artifact.role}`}
        >
          Open saved {artifact.role}
        </a>
      )}
    </figure>
  );
}
export default function History({
  runs,
  selected,
  onSelect,
  example = false,
}: {
  runs: SavedRun[];
  example?: boolean;
  selected?: SavedRun;
  onSelect: (run: SavedRun) => void;
}) {
  return (
    <div className="history">
      {!example && <div className="card card-heading">
        <div>
          <h2>Browser-local history</h2>
          <p>
            Read-only results saved on this device. Clearing site data or using
            another browser loses this history; start a new run if it is lost.
          </p>
        </div>
      </div>
      }
      {!example && !runs.length && (
        <div className="card empty">
          <h2>No saved terminal runs</h2>
          <p>
            No history was found in this browser. If site data was cleared,
            previous runs cannot be recovered; start a new run.
          </p>
        </div>
      )}
      <div className="history-list">
        {runs.map((run) => (
          <button
            className="card history-entry"
            key={run.id}
            onClick={() => onSelect(run)}
            aria-label={`Open run ${run.id}`}
          >
            <strong>{run.id}</strong>
            <span className={`status ${run.status}`}>{run.status}</span>
            <small>
              {new Date(run.createdAt).toLocaleString()} ·{" "}
              {run.patientIds.length} patients
            </small>
          </button>
        ))}
      </div>
      {selected && (
        <section className="card saved-run" aria-label="Saved run results">
          <div className="card-heading">
            <div>
              <h2>Saved run · {selected.status}</h2>
              <p>{selected.reason || "No terminal reason was supplied."}</p>
              <p>Read-only · engine is not rerun</p>
            </div>
          </div>
          {selected.events.some(e=>e.kind==="tool_result"&&e.payload.stage==="score") && <ScoreResults selectedIds={selected.patientIds} events={selected.events} />}
          {selected.events.some(e => e.kind === "tool_result" && e.payload.stage === "features") && <FeatureResults selectedIds={selected.patientIds}
            results={selected.events.filter(e => e.kind === "tool_result" && e.payload.stage === "features" && e.payload.patient).map(e => e.payload.patient)}
            qcResults={selected.events.filter(e => e.kind === "tool_result" && e.payload.stage === "qc").map(e => e.payload.patient)}
            maskResults={selected.events.filter(e => e.kind === "tool_result" && e.payload.stage === "masks").map(e => e.payload.patient)} />}
          {selected.events.filter(e => e.kind === "gate" && e.payload.report).map(e => <section key={e.id} aria-label="Recorded exclusion approval">
            <h3>Recorded exclusion disclosure</h3><p>Read-only audit · approval decision recorded in the timeline.</p>
            <p>{e.payload.report.scoring_eligible_count} scoring-eligible patients · {e.payload.report.evaluation_eligible_count} evaluation-eligible patients</p>
            <table><thead><tr><th>Patient</th><th>Scoring</th><th>Evaluation</th><th>Reason</th></tr></thead><tbody>{e.payload.report.dispositions.map((p:any) => <tr key={p.patient_id}><td>{p.patient_id}</td><td>{p.scoring_eligible ? "Eligible" : "Excluded"}</td><td>{p.evaluation_eligible ? "Eligible" : "Excluded"}</td><td>{p.reasons.map((r:any) => r.message).join("; ") || "Usable features and outcome"}</td></tr>)}</tbody></table>
          </section>)}
          <p>Selected patients: {selected.patientIds.join(", ")}</p>
          {Array.from(
            new Set([
              "qc",
              "masks",
              "features",
              selected.events.some(e => e.payload.stage === "score") ? "score" : "survival",
              ...selected.events.map((e) => e.payload.stage).filter(Boolean),
            ]),
          ).map((stage) => {
            const results = selected.events.filter(
              (e) => e.payload.stage === stage && (e.kind === "tool_result" || (stage === "eligibility" && e.payload.report)),
            );
            const called = selected.events.some(
              (e) => e.kind === "tool_call" && e.payload.stage === stage,
            );
            return (
              <article className="saved-stage" key={stage}>
                <h3>{stage}</h3>
                {!results.length ? (
                  <p className="muted">
                    {called
                      ? "Unfinished — no result saved"
                      : "Not run — no result saved"}
                  </p>
                ) : (
                  <>
                    {selected.patientIds
                      .filter(
                        (id) =>
                          !results.some(
                            (e) => e.payload.patient?.patient_id === id,
                          ) && results.some((e) => e.payload.patient),
                      )
                      .map((id) => (
                        <p className="muted" key={id}>
                          {id}: no {stage} result saved
                          {terminal(selected.status)
                            ? " before the run ended"
                            : ""}
                          .
                        </p>
                      ))}
                    {results.map((event) => (
                      <div key={event.id} className="saved-result">
                        <h4>
                          {event.payload.patient?.patient_id || stage} ·{" "}
                          {event.payload.patient?.status || "Result"}
                        </h4>
                        <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                      </div>
                    ))}
                  </>
                )}
                {selected.artifacts
                  .filter((a) => a.stage === stage)
                  .map((a) => (
                    <SavedArtifactView key={a.id} artifact={a} />
                  ))}
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}
