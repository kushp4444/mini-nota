import type { Audit } from "../lib/history";

export default function ScoreResults({ selectedIds, events }: { selectedIds: string[]; events: Audit[] }) {
  const scores = events.filter(e => e.kind === "tool_result" && e.payload.stage === "score").map(e => e.payload.patient);
  const report = events.find(e => e.payload.stage === "eligibility" && e.payload.report)?.payload.report;
  const stopped = events.find(e => e.kind === "done" && e.payload.status === "failed");
  return <section className="card results score-results" aria-label="Frozen model risk scores">
    <div className="card-heading"><div><h2>Model risk scores</h2><p>Relative model ranking · not survival probability or predicted lifespan</p></div><span>{scores.length} / {selectedIds.length} scored</span></div>
    {report?.model && <p className="model-context">Model {report.model.model_version} · Fixed development reference: {report.model.reference_count} patients. Held-out performance has not yet been evaluated.</p>}
    {stopped && <p className="model-context" role="status">{stopped.message}</p>}
    <div className="score-table"><table aria-label="Patient risk scores"><thead><tr><th>Patient</th><th>Risk score (log relative hazard)</th><th>Model version</th></tr></thead><tbody>{selectedIds.map(id => {
      const score = scores.find(p => p.patient_id === id);
      return <tr key={id}><td>{id}</td><td>{score ? score.values.risk_score.toPrecision(8) : "Not scored"}</td><td>{score?.values.model_version || "—"}</td></tr>;
    })}</tbody></table></div>
  </section>;
}
