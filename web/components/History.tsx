"use client";
import { useEffect, useState } from "react";
import BetaModelResults from "./BetaModelResults";
import EvaluationResults from "./EvaluationResults";
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
  selected,
  title,
  subtitle,
  faults,
  exampleFiles,
  onRecover,
}: {
  selected?: SavedRun;
  title?: string;
  subtitle?: string;
  faults?: string[];
  exampleFiles?: Record<string, string>;
  onRecover?: ArtifactRecovery;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const retained = usePatientResults(selected, exampleFiles);
  const hasResult = (...stages: string[]) => selected?.events.some(
    event => event.kind === "tool_result" && stages.includes(event.payload.stage),
  );
  const gates = selected?.events.filter(event => event.kind === "gate" && event.payload.report) ?? [];
  const showEvidence = selected?.status !== "completed" || gates.length > 0 || !hasResult("score", "evaluation") || !hasResult("features");
  const scanChecks = selected && <QCResults selectedIds={selected.patientIds} results={retained.qc ?? []} ended />;
  useEffect(() => setDetailsOpen(false), [selected?.id]);
  return (
    <section className="card saved-run" aria-label="Saved run results">
      {selected && <>
        <div className="example-run-heading">
          <h1 id="report-heading">{title ?? `Saved run · ${selected.status}`}</h1>
          <p>{selected.patientIds.length} {selected.patientIds.length === 1 ? "patient" : "patients"}{subtitle ? `. ${subtitle}` : ""}</p>
          {selected.status !== "completed" && selected.reason && <p>{selected.reason}</p>}
        </div>
        <nav className="example-section-links" aria-label="Run sections">
          <a href="#scans">Scans</a><a href="#measurements">Measurements</a><a href="#prototype-model">Model evaluation</a>
        </nav>
        {!!faults?.length && <div className="example-faults">
          <strong>Deliberately introduced fixture faults; the live library is unchanged.</strong>
          <ul>{faults.map(fault => <li key={fault}>{fault}</li>)}</ul>
        </div>}
      </>}
      <div id="scans">
        {selected && <>
          {showEvidence && scanChecks}
          <MaskResults key={selected.id} selectedIds={selected.patientIds} results={retained.masks ?? []} qcResults={retained.qc ?? []} ended compact>
            {!showEvidence && <details className="result-inner-details scan-checks-details"><summary>Scan checks</summary>{scanChecks}</details>}
          </MaskResults>
        </>}
      </div>
      {selected && <>
          <div id="measurements">
            <FeatureResults key={selected.id} selectedIds={selected.patientIds}
              results={retained.features ?? []}
              qcResults={retained.qc ?? []}
              maskResults={retained.masks ?? []} ended compact />
          </div>
          <BetaModelResults key={`model:${selected.id}`}>
            {hasResult("score", "evaluation")
              ? <ScoreResults selectedIds={selected.patientIds} events={selected.events} showBenchmark={false} compact />
              : !hasResult("survival") && <EvaluationResults ended />}
            <HeldOutBenchmark events={selected.events} compact />
          </BetaModelResults>
          {gates.map((e, index) => <section key={e.id} aria-label="Recorded exclusion approval">
            <h3>Recorded exclusion disclosure</h3><p>{gateStatus(selected, e, gates[index + 1])}</p>
            <p>{e.payload.report.scoring_eligible_count} scoring-eligible patients · {e.payload.report.evaluation_eligible_count} evaluation-eligible patients</p>
            <table><thead><tr><th>Patient</th><th>Scoring</th><th>Evaluation</th><th>Reason</th></tr></thead><tbody>{e.payload.report.dispositions.map((p:any) => <tr key={p.patient_id}><td>{p.patient_id}</td><td>{p.scoring_eligible ? "Eligible" : "Excluded"}</td><td>{p.evaluation_eligible ? "Eligible" : "Excluded"}</td><td>{p.reasons.map((r:any) => r.message).join("; ") || "Usable features and outcome"}</td></tr>)}</tbody></table>
          </section>)}
          <details key={`evidence:${selected.id}`} className="saved-evidence" open={showEvidence}><summary>Saved evidence</summary>
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
                  .filter((a) => a.stage === stage && !(stage === "masks" && a.role === "overlay" && a.mediaType === "image/png" && (exampleFiles?.[a.id] || (a.blob && !a.error))))
                  .map((a) => (
                    exampleFiles?.[a.id] ? <p key={a.id}><a href={exampleFiles[a.id]} download={`${a.patientId || stage}-${a.role}.${exampleFiles[a.id].split(".").pop()}`}>Open saved {a.role}</a></p> :
                    a.blob ? <SavedArtifactView key={a.id} artifact={a} /> :
                    <MissingArtifact key={a.id} run={selected} artifact={a} onRecover={onRecover} />
                  ))}
              </article>
            );
          })}
          </details>
      </>}
    </section>
  );
}
