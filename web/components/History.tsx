"use client";
import { useEffect, useState } from "react";
import FeatureResults from "./FeatureResults";
import ScoreResults, { HeldOutBenchmark } from "./ScoreResults";
import QCResults from "./QCResults";
import MaskResults from "./MaskResults";
import usePatientResults from "./usePatientResults";
import MissingArtifact, { type ArtifactRecovery } from "./MissingArtifact";
import { type Audit, type SavedArtifact, type SavedRun, terminal } from "../lib/history";
export function SavedArtifactView({ artifact }: { artifact: SavedArtifact }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!artifact.blob) return;
    const objectUrl = URL.createObjectURL(artifact.blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [artifact.blob]);
  if (!artifact.blob) return null;
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
function stageNames(events: Audit[]) {
  const observed = events.map(event => event.payload.stage).filter(Boolean);
  // Older saved runs used "survival"; retain that label when the audit contains it.
  const scoringStage = observed.includes("survival") && !observed.includes("score") ? "survival" : "score";
  return [...new Set(["qc", "masks", "features", scoringStage, ...observed])];
}

function gateStatus(run: SavedRun, gate: Audit, nextGate?: Audit) {
  const checkpoint = gate.payload.checkpoint;
  const approved = run.events.some(event => {
    if (event.sequence <= gate.sequence || (nextGate && event.sequence >= nextGate.sequence) ||
        event.kind !== "decision" || event.payload.action !== "approve") return false;
    // Legacy curated records omit checkpoint identity; use their recorded decision.
    return !checkpoint?.disclosure_id || (
      event.payload.disclosure_id === checkpoint.disclosure_id &&
      event.payload.model_version === checkpoint.model_version
    );
  });
  if (approved) return nextGate ? "Approval recorded. A later disclosure superseded this gate." : "Approval recorded.";
  if (nextGate) return "Superseded before approval.";
  return terminal(run.status) ? "Run ended before approval." : "Awaiting approval.";
}

export default function History({
  runs,
  selected,
  onSelect,
  onRecover,
  example = false,
}: {
  runs: SavedRun[];
  example?: boolean;
  selected?: SavedRun;
  onSelect: (run: SavedRun) => void;
  onRecover?: ArtifactRecovery;
}) {
  const [detailsOpen,setDetailsOpen] = useState(false);
  const retained = usePatientResults(selected);
  const gates = selected?.events.filter(event => event.kind === "gate" && event.payload.report) ?? [];
  useEffect(() => setDetailsOpen(false), [selected?.id]);
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
          <HeldOutBenchmark events={selected.events} />
          <QCResults selectedIds={selected.patientIds} results={retained.qc||[]} ended />
          <MaskResults selectedIds={selected.patientIds} results={retained.masks||[]} qcResults={retained.qc||[]} ended />
          {selected.events.some(e=>e.kind==="tool_result"&&e.payload.stage==="score") && <ScoreResults selectedIds={selected.patientIds} events={selected.events} showBenchmark={false} />}
          {selected.events.some(e => e.kind === "tool_result" && e.payload.stage === "features") && <FeatureResults selectedIds={selected.patientIds}
            results={retained.features||[]}
            qcResults={retained.qc||[]}
            maskResults={retained.masks||[]} ended />}
          {gates.map((e, index) => <section key={e.id} aria-label="Recorded exclusion approval">
            <h3>Recorded exclusion disclosure</h3><p>{gateStatus(selected, e, gates[index + 1])}</p>
            <p>{e.payload.report.scoring_eligible_count} scoring-eligible patients · {e.payload.report.evaluation_eligible_count} evaluation-eligible patients</p>
            <table><thead><tr><th>Patient</th><th>Scoring</th><th>Evaluation</th><th>Reason</th></tr></thead><tbody>{e.payload.report.dispositions.map((p:any) => <tr key={p.patient_id}><td>{p.patient_id}</td><td>{p.scoring_eligible ? "Eligible" : "Excluded"}</td><td>{p.evaluation_eligible ? "Eligible" : "Excluded"}</td><td>{p.reasons.map((r:any) => r.message).join("; ") || "Usable features and outcome"}</td></tr>)}</tbody></table>
          </section>)}
          <details><summary>Selected patients ({selected.patientIds.length})</summary><p>{selected.patientIds.join(", ")}</p></details>
          <details className="structured-details" onToggle={e=>setDetailsOpen(e.currentTarget.open)}><summary>Structured stage details</summary>{detailsOpen && selected.events.filter(e=>e.kind==='tool_result'||e.payload.report).map(event=><div className="saved-result" key={event.id}><h4>{event.payload.stage} · {event.payload.patient?.patient_id||'cohort'}</h4><pre>{JSON.stringify(event.payload,null,2)}</pre></div>)}</details>
          {stageNames(selected.events).map((stage) => {
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
                          {id}: {selected.events.some(e=>e.payload.stage==='qc'&&e.payload.patient?.patient_id===id&&e.payload.patient.status!=='success') ? 'excluded by QC — no' : selected.events.some(e=>e.payload.stage==='masks'&&e.payload.patient?.patient_id===id&&e.payload.patient.status!=='success') ? 'excluded by mask failure — no' : 'no'} {stage} result saved
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

                      </div>
                    ))}
                  </>
                )}
                {selected.artifacts
                  .filter((a) => a.stage === stage && !(stage === "masks" && a.role === "overlay" && a.mediaType === "image/png" && a.blob && !a.error))
                  .map((a) => (
                    a.blob ? <SavedArtifactView key={a.id} artifact={a} /> :
                    <MissingArtifact key={a.id} run={selected} artifact={a} onRecover={onRecover} />
                  ))}
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}
