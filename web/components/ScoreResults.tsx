import { useEffect, useState } from "react";
import EvaluationResults, { type Evaluation } from "./EvaluationResults";
import type { Audit } from "../lib/history";
import { riskFinding } from "../lib/survivalFindings";

export function HeldOutBenchmark({events}:{events:Audit[]}) {
  const [full,setFull] = useState<Evaluation>();
  useEffect(()=>{let active=true;fetch('/api/graphql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:'{ modelMetadata { evaluation { evaluation_version model_version scope c_index evaluated_count held_out_count event_count censored_count unavailable_reason time_unit exclusions { patient_id code message } uncertainty { context method interval estimable_samples unestimable_samples requested_samples } } } }'})}).then(r=>r.json()).then(r=>{if(active)setFull(r.data?.modelMetadata?.evaluation?.evaluation_version?r.data.modelMetadata.evaluation:undefined);}).catch(()=>{});return()=>{active=false;};},[]);
  const savedModel = events.find(e=>e.kind==='plan'&&e.payload.model)?.payload.model;
  const baseline = savedModel ? (savedModel.evaluation?.evaluation_version ? savedModel.evaluation : undefined) : full;
  return <EvaluationResults evaluation={baseline} full />;
}

type PatientScore = {
  patient_id: string;
  values: {
    risk_score?: number;
    risk_percentile?: number | null;
    risk_group?: string;
    model_version?: string;
  };
};

function modelRiskGroup(group?: string) {
  if (group === "higher model risk") return "Higher model risk (above the reference group’s middle score)";
  if (group === "lower model risk") return "Lower model risk (at or below the reference group’s middle score)";
  return "Model-risk group unavailable";
}

export default function ScoreResults({ selectedIds, events, showBenchmark = true }: {
  selectedIds: string[];
  events: Audit[];
  showBenchmark?: boolean;
}) {
  const exploratory = events.find(e => e.kind === "tool_result" && e.payload.stage === "evaluation")?.payload.evaluation;
  const scores: PatientScore[] = events.filter(e => e.kind === "tool_result" && e.payload.stage === "score")
    .map(e => e.payload.patient).filter(Boolean);
  const scoresById = new Map(scores.map(score => [score.patient_id, score.values]));
  const report = events.find(e => e.payload.stage === "eligibility" && e.payload.report)?.payload.report;
  const terminal = events.find(e => e.kind === "done");
  const stopped = terminal && ["failed", "canceled", "interrupted"].includes(terminal.payload.status);
  return <section className="card results score-results" aria-label="Frozen model risk scores">
    <div className="card-heading">
      <h2>Model risk scores</h2>
      <span>{scores.length} / {selectedIds.length} scored</span>
    </div>
    {stopped && <p className="model-context" role="status">{terminal.message}</p>}
    {showBenchmark && <HeldOutBenchmark events={events} />}
    {scores.length ? <>
      <div className="patient-risk-findings">
        {scores.map(({ patient_id, values }) => <div key={patient_id}>
          <p className="result-finding">{riskFinding(patient_id, values.risk_percentile)}</p>
          <p className="result-caption">
            {values.risk_percentile != null ? `Reference percentile ${values.risk_percentile.toFixed(1)} · ` : ""}
            {modelRiskGroup(values.risk_group)}
          </p>
        </div>)}
      </div>
      <details className="result-details">
        <summary>View details</summary>
        {report?.model && <p className="model-context">
          Model {report.model.model_version} · Fixed development reference {report.model.reference_count} patients
          {report.model.reference_median != null && ` · Median score ${report.model.reference_median.toPrecision(6)}`}
        </p>}
        <div className="score-table" tabIndex={0} role="region" aria-label="Scrollable patient risk scores">
          <table aria-label="Patient risk scores">
            <thead><tr><th>Patient</th><th>Risk score (log relative hazard)</th><th>Development percentile</th><th>Fixed model-risk group</th><th>Model version</th></tr></thead>
            <tbody>{selectedIds.map(id => {
              const values = scoresById.get(id);
              return <tr key={id}>
                <td>{id}</td>
                <td>{values ? values.risk_score?.toPrecision(8) ?? "—" : "Not scored"}</td>
                <td>{values?.risk_percentile != null ? values.risk_percentile.toFixed(1) : "—"}</td>
                <td>{values?.risk_group || "—"}</td>
                <td>{values?.model_version || "—"}</td>
              </tr>;
            })}</tbody>
          </table>
        </div>
        <p>Percentiles count reference scores at or below each patient’s score, including ties. The higher group contains scores above the middle score of the patients the model learned from. These results describe rank. They cannot predict how long a patient will live.</p>
      </details>
    </> : <p className="result-finding">{terminal
      ? "This run ended before a risk score was available."
      : "Eligible patients receive risk scores after imaging and any required approval."}</p>}
    <EvaluationResults evaluation={exploratory} ended={Boolean(terminal)} />
  </section>;
}
