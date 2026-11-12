"use client";
import { useState } from "react";
import type { SavedRun } from "../lib/history";
export default function ApprovalGate({ run, onApprove }: { run: SavedRun; onApprove: () => Promise<void> }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const checkpoint = run.checkpoint as {model_version:string;eligibility:{scoring_eligible_count:number;evaluation_eligible_count:number;dispositions:{patient_id:string;scoring_eligible:boolean;evaluation_eligible:boolean;reasons:{message:string}[]}[]}};
  if (run.status !== "waiting_approval" || !checkpoint) return null;
  const report = checkpoint.eligibility;
  return <section className="card approval-gate" aria-label="Patient exclusion approval">
    <div className="card-heading"><div><h2>Review patient exclusions</h2><p>Approve this disclosed cohort before frozen-model scoring.</p></div></div>
    <p>{report.scoring_eligible_count} scoring-eligible patients · {report.evaluation_eligible_count} evaluation-eligible patients</p>
    <p>Model: {checkpoint.model_version}</p>
    <table><thead><tr><th>Patient</th><th>Scoring</th><th>Evaluation</th><th>Reason</th></tr></thead><tbody>{report.dispositions.map(p => <tr key={p.patient_id}><td>{p.patient_id}</td><td>{p.scoring_eligible ? "Eligible" : "Excluded"}</td><td>{p.evaluation_eligible ? "Eligible" : "Excluded"}</td><td>{p.reasons.map(r => r.message).join("; ") || "Usable features and outcome"}</td></tr>)}</tbody></table>
    <p>Missing outcomes exclude evaluation only. Waiting has no deadline and holds no active computation slot. Approval is an anonymous action for this run.</p>
    {error && <p role="alert">{error}</p>}
    <button className="primary" disabled={busy} onClick={async () => {setBusy(true);setError("");try {await onApprove();} catch(e) {setError(e instanceof Error ? e.message : "Approval unavailable");} finally {setBusy(false);}}}>{busy ? "Verifying disclosed cohort…" : "Approve disclosed cohort and score"}</button>
  </section>;
}
