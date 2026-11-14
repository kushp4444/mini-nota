import { evaluationFinding, survivalCurveFinding } from "../lib/survivalFindings";

type Curve = {
  group: string;
  count: number;
  events: number;
  points: { time: number; survival: number }[];
};
export type Evaluation = {
  evaluation_version?: string;
  model_version?: string;
  c_index: number | null;
  evaluated_count: number;
  event_count: number;
  censored_count: number;
  unavailable_reason?: string | null;
  method?: string;
  time_unit: string;
  curves?: Curve[];
  exclusions: { patient_id: string; code: string; message: string }[];
  uncertainty?: {
    context: string;
    method?: string;
    interval?: number[] | null;
    estimable_samples?: number;
    unestimable_samples?: number;
    requested_samples?: number;
  };
};

export default function EvaluationResults({ evaluation, full = false, ended = false }: {
  evaluation?: Evaluation;
  full?: boolean;
  ended?: boolean;
}) {
  const interval = evaluation?.uncertainty?.interval;
  const curves = evaluation?.curves ?? [];
  return <section className="evaluation-result" aria-label={full ? "Full held-out evaluation" : "Selected cohort exploratory evaluation"}>
    <h3>{full ? "Full held-out evaluation" : "Selected cohort · exploratory"}</h3>
    {!evaluation ? <p className="result-finding">{full
      ? "Full held-out evaluation is unavailable for the deployed model."
      : ended ? "This run ended before exploratory evaluation was available."
      : "Exploratory outcome evaluation appears after scoring."}</p> : <>
      <p className="result-finding">{evaluationFinding(evaluation)}</p>
      <p className="result-caption">
        {evaluation.c_index == null ? "C-index unavailable" : `C-index ${evaluation.c_index.toFixed(3)}`}
        {interval?.length === 2 && ` · 95% patient-bootstrap interval ${interval[0].toFixed(3)}–${interval[1].toFixed(3)}`}
        {" · "}{evaluation.evaluated_count} patients evaluated · {evaluation.event_count} events · {evaluation.censored_count} censored
      </p>
      <p>{full
        ? "The model was tested on the full group of patients set aside before development, regardless of your selection."
        : "This exploratory result uses only selected patients with scores and usable outcomes."}</p>
      <p>C-index measures how often higher model scores went with shorter observed survival among patient pairs whose outcomes can be ordered.</p>
      {evaluation.exclusions.length > 0 && <div>
        <h4>Excluded from evaluation</h4>
        <ul>{evaluation.exclusions.map(e => <li key={e.patient_id}>{e.patient_id} · {e.message}</li>)}</ul>
      </div>}
      {!full && <>
        <p>{survivalCurveFinding(curves)}</p>
        {curves.length > 0 && <SurvivalChart curves={curves} unit={evaluation.time_unit} />}
      </>}
      <details>
        <summary>View details</summary>
        {evaluation.model_version && <p>Model {evaluation.model_version}</p>}
        {evaluation.evaluation_version && <p>Evaluation {evaluation.evaluation_version}</p>}
        <p>Harrell concordance gives tied scores half credit and applies lifelines rules to censored outcomes.</p>
        {evaluation.uncertainty?.method && <p>{evaluation.uncertainty.method}</p>}
        {evaluation.uncertainty?.requested_samples != null && <p>
          {evaluation.uncertainty.estimable_samples} estimable / {evaluation.uncertainty.requested_samples} samples
          {" · "}{evaluation.uncertainty.unestimable_samples} unestimable
        </p>}
        {evaluation.uncertainty?.context && <p>{evaluation.uncertainty.context}</p>}
        {full && interval && <p>The interval measures uncertainty on the held-out cohort for the frozen fitted model.</p>}
      </details>
    </>}
  </section>;
}

function SurvivalChart({curves,unit}:{curves:Curve[];unit:string}) {
  const max=Math.max(1,...curves.flatMap(c=>c.points.map(p=>p.time)));
  const x=(t:number)=>54+t/max*500,y=(s:number)=>220-s*180;
  return <><svg viewBox="0 0 600 275" role="img" aria-label="Observed Kaplan–Meier survival" style={{width:'100%',maxWidth:700}}>
    <path d="M54 40 V220 H554" fill="none" stroke="#9ca3af"/>
    {[0,.5,1].map(s=><g key={s}><text x="44" y={y(s)+4} textAnchor="end" fontSize="12">{s}</text><path d={`M54 ${y(s)} H554`} stroke="#e5e7eb"/></g>)}
    {[0,.5,1].map(t=><text key={t} x={x(t*max)} y="239" textAnchor="middle" fontSize="12">{Math.round(t*max)}</text>)}
    <text x="300" y="265" textAnchor="middle" fontSize="13">Recorded follow-up ({unit})</text><text x="55" y="25" fontSize="13">Observed survival</text>
    {curves.map(c=>{let d=`M${x(0)} ${y(1)}`;for(const p of c.points)d+=` H${x(p.time)} V${y(p.survival)}`;return <path key={c.group} d={d} stroke={c.group==='higher model risk'?'#dc6b30':'#267f91'} strokeWidth="2.5" fill="none"/>;})}
  </svg><ul>{curves.map(c=><li key={c.group} style={{color:c.group==='higher model risk'?'#a94716':'#186778'}}>{c.group} · n={c.count}, {c.events} events</li>)}</ul><p>The chart summarizes observed survival using groups defined by the median score of the patients the model learned from.</p></>;
}
