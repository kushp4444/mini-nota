type Curve = {group:string;count:number;events:number;points:{time:number;survival:number}[]};
export type Evaluation = {evaluation_version?:string;model_version?:string;scope?:string;c_index:number|null;evaluated_count:number;held_out_count?:number;event_count:number;censored_count:number;unavailable_reason?:string;time_unit:string;curves?:Curve[];curve_context?:string;exclusions:{patient_id:string;code:string;message:string}[];uncertainty:{context:string;method?:string;interval?:number[];estimable_samples?:number;unestimable_samples?:number;requested_samples?:number}};

export default function EvaluationResults({evaluation,full=false}:{evaluation?:Evaluation;full?:boolean}) {
  return <section className="evaluation-result" aria-label={full?'Full held-out evaluation':'Selected cohort exploratory evaluation'}>
    <h3>{full?'Full held-out evaluation':'Selected cohort · exploratory'}</h3>
    {!evaluation ? <p>{full?'Full held-out evaluation is unavailable for the deployed model.':'Exploratory outcome evaluation appears after scoring.'}</p> : <>
      <p><strong>{evaluation.c_index==null?'C-index unavailable':evaluation.c_index.toFixed(3)}</strong> {evaluation.c_index!=null&&'c-index'} · {evaluation.evaluated_count} evaluated · {evaluation.event_count} events · {evaluation.censored_count} censored</p>
      {evaluation.unavailable_reason&&<p>{evaluation.unavailable_reason}</p>}
      {full&&<><p>Fixed full held-out cohort; this result stays the same when your selection changes. Model {evaluation.model_version}.</p><p>Evaluation {evaluation.evaluation_version}</p></>}
      {evaluation.uncertainty.interval&&<p>95% patient-bootstrap interval: {evaluation.uncertainty.interval[0].toFixed(3)}–{evaluation.uncertainty.interval[1].toFixed(3)}. {evaluation.uncertainty.estimable_samples} estimable / {evaluation.uncertainty.requested_samples} samples; {evaluation.uncertainty.unestimable_samples} unestimable.</p>}
      <p>{evaluation.uncertainty.context} {full&&'Interval conditions on the frozen fitted model; it does not include uncertainty from model development.'}</p>
      <p>Evaluation exclusions: {evaluation.exclusions.length}.{evaluation.exclusions.map(e=><span key={e.patient_id}> {e.patient_id}: {e.message}.</span>)}</p>
      {!full&&<><p>{evaluation.curve_context}</p>{Boolean(evaluation.curves?.length)&&<SurvivalChart curves={evaluation.curves!} unit={evaluation.time_unit}/>}</>}
      {full&&<details><summary>Evaluation method</summary><p>Harrell concordance: higher log-risk predicts shorter observed survival. Risk ties receive half credit; censored pairs follow lifelines admissibility rules. Concordance measures ordering among comparable outcomes, not a percentage of patients predicted correctly.</p><p>{evaluation.uncertainty.method}</p></details>}
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
  </svg><ul>{curves.map(c=><li key={c.group} style={{color:c.group==='higher model risk'?'#a94716':'#186778'}}>{c.group} · n={c.count}, {c.events} events</li>)}</ul><p>Observed outcomes within relative model groups, using the fixed development median. These are not clinical risk categories or predicted survival probabilities. Curves are unadjusted exploratory summaries; no curve separation is assumed.</p></>;
}
