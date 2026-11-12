import { useEffect, useState } from "react";
import EvaluationResults, { type Evaluation } from "./EvaluationResults";
import type { Audit } from "../lib/history";

export default function ScoreResults({ selectedIds, events }: { selectedIds: string[]; events: Audit[] }) {
  const [full,setFull] = useState<Evaluation>();
  useEffect(()=>{let active=true;fetch('/api/graphql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:'{ modelMetadata { evaluation { evaluation_version model_version scope c_index evaluated_count held_out_count event_count censored_count unavailable_reason time_unit exclusions { patient_id code message } uncertainty { context method interval estimable_samples unestimable_samples requested_samples } } } }'})}).then(r=>r.json()).then(r=>{if(active)setFull(r.data?.modelMetadata?.evaluation?.evaluation_version?r.data.modelMetadata.evaluation:undefined);}).catch(()=>{});return()=>{active=false;};},[]);
  const savedModel = events.find(e=>e.kind==='plan'&&e.payload.model)?.payload.model;
  const baseline = savedModel ? (savedModel.evaluation?.evaluation_version ? savedModel.evaluation : undefined) : full;
  const exploratory = events.find(e=>e.kind==='tool_result'&&e.payload.stage==='evaluation')?.payload.evaluation;
  const scores = events.filter(e => e.kind === "tool_result" && e.payload.stage === "score").map(e => e.payload.patient);
  const report = events.find(e => e.payload.stage === "eligibility" && e.payload.report)?.payload.report;
  const stopped = events.find(e => e.kind === "done" && e.payload.status === "failed");
  return <section className="card results score-results" aria-label="Frozen model risk scores">
    <div className="card-heading"><div><h2>Model risk scores</h2><p>Relative model ranking · not survival probability or predicted lifespan</p></div><span>{scores.length} / {selectedIds.length} scored</span></div>
    {report?.model && <p className="model-context">Model {report.model.model_version} · Fixed development reference: {report.model.reference_count} patients · fixed median {report.model.reference_median?.toPrecision(6)}.</p>}
    {stopped && <p className="model-context" role="status">{stopped.message}</p>}
    <div className="score-table"><table aria-label="Patient risk scores"><thead><tr><th>Patient</th><th>Risk score (log relative hazard)</th><th>Development percentile</th><th>Fixed model-risk group</th><th>Model version</th></tr></thead><tbody>{selectedIds.map(id => {
      const score = scores.find(p => p.patient_id === id);
      return <tr key={id}><td>{id}</td><td>{score ? score.values.risk_score.toPrecision(8) : "Not scored"}</td><td>{score?.values.risk_percentile != null ? `${score.values.risk_percentile.toFixed(1)}th` : "—"}</td><td>{score?.values.risk_group || "—"}</td><td>{score?.values.model_version || "—"}</td></tr>;
    })}</tbody></table></div>
    <p>Percentile is 100 × the fraction of frozen development-reference scores at or below this score. Ties receive the upper empirical rank. Higher model risk is strictly above the development median; at or below is lower model risk. These fixed relative rankings are not probabilities of death, lifespan estimates, or clinical risk categories.</p>
    <EvaluationResults evaluation={baseline} full />
    <EvaluationResults evaluation={exploratory} />
  </section>;
}
