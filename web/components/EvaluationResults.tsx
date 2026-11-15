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
  const exclusions = evaluation?.exclusions ?? [];
  return <section className="evaluation-result" aria-label={full ? "How the model did on its test group" : "What happened to the patients you selected"}>
    <h3>{full ? "How the model did on its test group" : "What happened to the patients you selected"}</h3>
    {!evaluation ? <p className="result-finding">{full
      ? "There are no test results to show for this model."
      : ended ? "This run ended before we could check how the scores compared with what happened to the patients."
      : "Once the patients are scored, we’ll check how the scores compare with their records."}</p> : <>
      <p className="result-finding">{evaluationFinding(evaluation)}</p>
      <p className="result-caption">
        {evaluation.c_index == null ? "C-index unavailable" : `C-index ${evaluation.c_index.toFixed(3)}`}
        {interval?.length === 2 && ` · 95% confidence interval ${interval[0].toFixed(3)}–${interval[1].toFixed(3)}`}
        {" · "}{evaluation.evaluated_count} {evaluation.evaluated_count === 1 ? "patient" : "patients"} with usable records · {evaluation.event_count} recorded {evaluation.event_count === 1 ? "death" : "deaths"} · {evaluation.censored_count} without a recorded death during follow-up
      </p>
      <p>{full
        ? "These patients were set aside before the model learned. Your selection doesn’t change this test."
        : "The model scores each selected patient separately. We compare those patients with each other using their scores and follow-up records. The patients the model learned from are used to explain where each score ranks."}</p>
      {exclusions.length > 0 && <div>
        <h4>Whose records couldn’t be used</h4>
        <ul>{exclusions.map(e => <li key={e.patient_id}>{e.patient_id} · {e.message}</li>)}</ul>
      </div>}
      {!full && <>
        <p>{survivalCurveFinding(curves)}</p>
        {curves.length > 0 && <SurvivalChart curves={curves} unit={evaluation.time_unit} />}
      </>}
      <details>
        <summary>View details</summary>
        <p>C-index checks how often the model gave a higher score to the patient who died sooner, among people whose records could be compared. A score of 0.5 is what you’d expect from guessing.</p>
        {evaluation.unavailable_reason && <p>{evaluation.unavailable_reason}</p>}
        {evaluation.model_version && <p>Model {evaluation.model_version}</p>}
        {evaluation.evaluation_version && <p>Evaluation {evaluation.evaluation_version}</p>}
        <p>If two patients have the same score, the comparison counts as half right.</p>
        {evaluation.uncertainty?.requested_samples != null && <p>
          {evaluation.uncertainty.estimable_samples} samples with a result out of {evaluation.uncertainty.requested_samples} samples
          {" · "}{evaluation.uncertainty.unestimable_samples} without a result
        </p>}
        {full && interval && <p>The interval shows how much the test score might vary if we tested the same model on another group like this one.</p>}
      </details>
    </>}
  </section>;
}

function SurvivalChart({curves,unit}:{curves:Curve[];unit:string}) {
  const drops = curves.flatMap(curve => curve.points.flatMap((point, index) => {
    const previous = curve.points[index - 1]?.survival ?? 1;
    return point.survival < previous ? [{ ...point, previous }] : [];
  }));
  const dropTimes = [...new Set(drops.map(drop => drop.time))].sort((a, b) => a - b);
  const bothDeathsObserved = curves.length === 1 && curves[0].count === 2 && curves[0].events === 2;
  const max = Math.max(1, ...curves.flatMap(curve => curve.points.map(point => point.time)));
  const x = (time: number) => 54 + time / max * 500;
  const y = (survival: number) => 220 - survival * 180;
  const rowEnds: number[] = [x(0) + 6];
  const labels = dropTimes.map(time => {
    const width = Math.max(30, String(time).length * 13);
    const row = rowEnds.findIndex(end => x(time) - width / 2 > end + 6);
    const labelRow = row === -1 ? rowEnds.length : row;
    rowEnds[labelRow] = x(time) + width / 2;
    return { time, row: labelRow };
  });
  const axisTitleY = 265 + Math.max(0, rowEnds.length - 1) * 20;
  return <>
    {bothDeathsObserved && dropTimes.length === 2 && <p>
      One patient died at {dropTimes[0]} {unit} and the other at {dropTimes[1]} {unit} after follow-up began.
    </p>}
    <svg viewBox={`0 0 600 ${axisTitleY + 10}`} role="img" aria-label="Estimated percentage of patients still alive over time" style={{width: "100%", maxWidth: 700}}>
      <path d="M54 40 V220 H554" fill="none" stroke="var(--color-rule-2)"/>
      {[0, 0.5, 1].map(s => <g key={s}>
        <text x="44" y={y(s) + 4} textAnchor="end" fontSize="12">{s * 100}%</text>
        <path d={`M54 ${y(s)} H554`} stroke="var(--color-rule)"/>
      </g>)}
      {curves.map(curve => {
        const path = curve.points.reduce((d, point) => `${d} H${x(point.time)} V${y(point.survival)}`, `M${x(0)} ${y(1)}`);
        return <path key={curve.group} d={path} stroke={curve.group === "higher model risk" ? "var(--color-accent)" : "var(--color-ink-2)"} strokeWidth="2.5" strokeDasharray={curve.group === "higher model risk" ? undefined : "6 4"} fill="none"/>;
      })}
      {drops.map(({ time, survival, previous }, index) => <line key={index}
        x1={x(time)} x2={x(time)} y1={y(survival === 0 ? previous : survival)} y2={y(0)}
        stroke="var(--color-muted)" strokeWidth="1.25" strokeDasharray="2 3"
      />)}
      <text x={x(0)} y="239" textAnchor="middle" fontSize="12">0</text>
      {!dropTimes.length && <text x={x(max)} y="239" textAnchor="middle" fontSize="12">{max}</text>}
      {labels.map(({ time, row }) => <g key={time}>
        <line x1={x(time)} x2={x(time)} y1="220" y2={226 + row * 20} stroke="var(--color-muted)" strokeDasharray="2 3"/>
        <text x={x(time)} y={239 + row * 20} textAnchor="middle" fontSize="12">{time}</text>
      </g>)}
      <text x="300" y={axisTitleY} textAnchor="middle" fontSize="13">Time since follow-up began ({unit})</text>
      <text x="55" y="25" fontSize="13">Estimated percentage still alive</text>
    </svg>
    <ul>{curves.map(curve => <li key={curve.group} style={{color: curve.group === "higher model risk" ? "var(--color-accent)" : "var(--color-ink-2)"}}>
      {curve.group === "higher model risk" ? "Higher scores" : "Lower scores"} · {curve.count} {curve.count === 1 ? "patient" : "patients"}, {curve.events} recorded {curve.events === 1 ? "death" : "deaths"}
    </li>)}</ul>
    <p>A drop marks one or more recorded deaths. The dotted lines show when they happened.</p>
  </>;
}
