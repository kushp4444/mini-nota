import { evaluationFinding, survivalCurveFinding } from "../lib/survivalFindings";

type Curve = {
  group: string;
  count: number;
  events: number;
  points: { time: number; survival: number }[];
};
type PatientFollowUp = { patient_id: string; duration: number; death_recorded: boolean; group: string };

export type Evaluation = {
  evaluation_version?: string;
  model_version?: string;
  c_index: number | null;
  evaluated_count: number;
  evaluated_patients?: string[];
  patient_follow_up?: PatientFollowUp[];
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

export default function EvaluationResults({ evaluation, full = false, ended = false, patientSummary, compact = false }: {
  evaluation?: Evaluation;
  full?: boolean;
  ended?: boolean;
  patientSummary?: React.ReactNode;
  compact?: boolean;
}) {
  const interval = evaluation?.uncertainty?.interval;
  const curves = evaluation?.curves ?? [];
  const exclusions = evaluation?.exclusions ?? [];
  const higher = curves.find(curve => curve.group === "higher model risk");
  const lower = curves.find(curve => curve.group === "lower model risk");
  const comparisonDay = 200;
  const atComparisonDay = (curve?: Curve) =>
    (curve?.points.at(-1)?.time ?? 0) >= comparisonDay
      ? curve?.points.findLast(point => point.time <= comparisonDay)?.survival
      : undefined;
  const higherSurvival = atComparisonDay(higher);
  const lowerSurvival = atComparisonDay(lower);
  const firstDrop = (curve?: Curve) => curve?.points.find(point => point.survival < 1)?.time ?? Infinity;
  const showComparison = compact && !full && higher && lower;
  const earlierDrop = firstDrop(higher) < firstDrop(lower);
  return <section className={full && compact ? "evaluation-result example-benchmark" : "evaluation-result"} aria-label={full ? "How the model did on its test group" : "What happened to the patients you selected"}>
    <div className={compact ? "example-section-heading" : undefined}>
      <h3>{full ? (compact ? "Across the test group" : "How the model did on its test group") : compact ? "What happened?" : "What happened to the patients you selected"}</h3>
      {compact && !full && <span>Selected patients</span>}
    </div>
    {!evaluation ? <p className="result-finding">{full
      ? "There are no test results to show for this model."
      : ended ? "This run ended before we could check how the scores compared with what happened to the patients."
      : "Waiting for scores and follow-up records."}</p> : <>
      {compact && evaluation.evaluated_count === 2 && evaluation.event_count === 2 && evaluation.c_index === 0
        ? <div className="example-finding"><h4>The higher-ranked patient lived longer.</h4><p>The model got this pair’s order backward.</p></div>
        : showComparison ? <div className="example-finding">
          <h4>{earlierDrop ? "Survival fell sooner in the higher-score group." : "Survival by model score."}</h4>
          {higherSurvival != null && lowerSurvival != null && <p>At day {comparisonDay}, estimated survival from follow-up was <strong>{Math.round(higherSurvival * 100)}% for patients with higher model scores</strong> and <strong>{Math.round(lowerSurvival * 100)}% for patients with lower model scores</strong>.</p>}
        </div> : <p className="result-finding">{evaluationFinding(evaluation)}</p>}
      {!compact && <p className="result-caption">
        {evaluation.c_index == null ? "C-index unavailable" : `C-index ${evaluation.c_index.toFixed(3)}`}
        {interval?.length === 2 && ` · 95% confidence interval ${interval[0].toFixed(3)}–${interval[1].toFixed(3)}`}
        {" · "}{evaluation.evaluated_count} {evaluation.evaluated_count === 1 ? "patient" : "patients"} with usable records · {evaluation.event_count} recorded {evaluation.event_count === 1 ? "death" : "deaths"} · {evaluation.censored_count} without a recorded death during follow-up
      </p>}
      {exclusions.length > 0 && <div>
        <h4>Whose records couldn’t be used</h4>
        <ul>{exclusions.map(e => <li key={e.patient_id}>{e.patient_id} · {e.message}</li>)}</ul>
      </div>}
      {!full && <div className="survival-comparison">
        <div>
          {curves.length > 0 && <SurvivalChart curves={curves} unit={evaluation.time_unit} compact={compact} followUp={evaluation.patient_follow_up} />}
          {(!compact || curves.length < 2) && <p className="result-caption">{compact && curves.length === 1 && curves[0].count === evaluation.evaluated_count ? `All evaluated patients were in the ${curves[0].group === "higher model risk" ? "higher" : "lower"}-score group.` : survivalCurveFinding(curves)}</p>}
        </div>
        {patientSummary}
      </div>}
      <details>
        <summary>{compact ? (full ? `${evaluation.evaluated_count} patients. View evidence` : "How to read this result") : "View details"}</summary>
        {compact && <p className="result-caption">
        {evaluation.c_index == null ? "C-index unavailable" : `C-index ${evaluation.c_index.toFixed(3)}`}
        {interval?.length === 2 && ` · 95% confidence interval ${interval[0].toFixed(3)}–${interval[1].toFixed(3)}`}
        {" · "}{evaluation.evaluated_count} {evaluation.evaluated_count === 1 ? "patient" : "patients"} with usable records · {evaluation.event_count} recorded {evaluation.event_count === 1 ? "death" : "deaths"} · {evaluation.censored_count} without a recorded death during follow-up
      </p>}
        {full && <p>These patients were set aside before the model learned. Your selection doesn’t change this test.</p>}
        {showComparison && <p>{evaluationFinding(evaluation)}</p>}
        {evaluation.patient_follow_up?.some(patient => !patient.death_recorded) && <p>Short marks show the last known follow-up without a recorded death.</p>}
        <p>Take two patients whose records tell us who died sooner. Did the model give that patient the higher risk score? The C-index sums up how often the model got that order right. Guessing gives about 0.5 overall.</p>
        <p>If both patients got the same risk score, the model didn’t pick an order. That pair adds half a point to the tally.</p>
        {evaluation.unavailable_reason && <p>{evaluation.unavailable_reason}</p>}
        {evaluation.model_version && <p>Model {evaluation.model_version}</p>}
        {evaluation.evaluation_version && <p>Evaluation {evaluation.evaluation_version}</p>}
        {evaluation.uncertainty?.requested_samples != null && <p>
          {evaluation.uncertainty.estimable_samples} samples with a result out of {evaluation.uncertainty.requested_samples} samples
          {" · "}{evaluation.uncertainty.unestimable_samples} without a result
        </p>}
        {full && interval && <p>The interval shows how much the test score might vary if we tested the same model on another group like this one.</p>}
      </details>
    </>}
    {!evaluation && patientSummary}
  </section>;
}

function SurvivalChart({curves,unit,compact,followUp = []}:{curves:Curve[];unit:string;compact:boolean;followUp?:PatientFollowUp[]}) {
  const drops = curves.flatMap(curve => curve.points.flatMap((point, index) => {
    const previous = curve.points[index - 1]?.survival ?? 1;
    return point.survival < previous ? [{ ...point, previous }] : [];
  }));
  const dropTimes = [...new Set(drops.map(drop => drop.time))].sort((a, b) => a - b);
  const bothDeathsObserved = curves.length === 1 && curves[0].count === 2 && curves[0].events === 2;
  const max = Math.max(1, ...curves.flatMap(curve => curve.points.map(point => point.time)));
  const x = (time: number) => 54 + time / max * 500;
  const baseline = compact ? 230 : 220;
  const tickY = compact && curves.length > 1 ? 253 : compact ? 254 : 239;
  const y = (survival: number) => baseline - survival * 180;
  const denseTimes = dropTimes.length > 6;
  const tickStep = Math.max(1, 10 ** Math.floor(Math.log10(max)));
  const labelTimes = denseTimes
    ? Array.from({length: Math.floor(max / tickStep)}, (_, index) => (index + 1) * tickStep)
    : dropTimes;
  const rowPositions: number[][] = [[x(0)]];
  const labels = labelTimes.map((time, index) => {
    const preferred = !denseTimes && compact && curves.length > 1 ? index % 2 : 0;
    let row = preferred;
    while (rowPositions[row]?.some(position => Math.abs(position - x(time)) < 29)) row++;
    (rowPositions[row] ??= []).push(x(time));
    return { time, row };
  });
  const rowPitch = compact ? 17 : 20;
  const axisTitleY = (compact ? 282 : 265) + Math.max(0, rowPositions.length - 1) * (compact ? 14 : 20);
  return <>
    {!compact && bothDeathsObserved && dropTimes.length === 2 && <p>
      One patient died at {dropTimes[0]} {unit} and the other at {dropTimes[1]} {unit} after follow-up began.
    </p>}
    <svg viewBox={`0 0 600 ${axisTitleY + (compact ? 8 : 10)}`} role="img" aria-label="Estimated percentage of patients still alive over time" style={{width: "100%", maxWidth: 700}}>
      {!compact && <path d="M54 40 V220 H554" fill="none" stroke="var(--color-rule-2)"/>}
      {[0, 0.5, 1].map(s => <g key={s}>
        <text x="44" y={y(s) + 4} textAnchor="end" fontSize={compact && curves.length > 1 ? 13 : 12}>{s * 100}%</text>
        <path d={`M54 ${y(s)} H554`} stroke="var(--color-rule)"/>
      </g>)}
      {curves.map(curve => {
        const path = curve.points.reduce((d, point) => `${d} H${x(point.time)} V${y(point.survival)}`, `M${x(0)} ${y(1)}`);
        return <path key={curve.group} d={path} stroke={curve.group === "higher model risk" ? "var(--color-accent)" : "var(--color-ink-2)"} strokeWidth="2.5" strokeDasharray={curve.group === "higher model risk" ? undefined : "6 4"} fill="none"/>;
      })}
      {followUp.filter(patient => !patient.death_recorded).map(patient => {
        const curve = curves.find(series => series.group === patient.group);
        const survival = curve?.points.findLast(point => point.time <= patient.duration)?.survival ?? 1;
        return <path key={patient.patient_id} d={`M${x(patient.duration)} ${y(survival) - 5}v10`}
          stroke={patient.group === "higher model risk" ? "var(--color-accent)" : "var(--color-ink-2)"} strokeWidth="2" />;
      })}
      {!denseTimes && drops.map(({ time, survival, previous }, index) => <line key={index}
        x1={x(time)} x2={x(time)} y1={y(survival === 0 ? previous : survival)} y2={y(0) + (compact && curves.length > 1 ? 8 : 0)}
        stroke="var(--color-muted)" strokeWidth="1.25" strokeDasharray="2 3"
      />)}
      <text x={x(0)} y={tickY} textAnchor="middle" fontSize={compact && curves.length > 1 ? 13 : 12}>0</text>
      {!dropTimes.length && <text x={x(max)} y={tickY} textAnchor="middle" fontSize={compact && curves.length > 1 ? 13 : 12}>{max}</text>}
      {labels.map(({ time, row }) => <g key={time}>
        {(!compact || curves.length === 1) && <line x1={x(time)} x2={x(time)} y1={baseline} y2={baseline + (compact ? 9 : 6) + row * rowPitch} stroke="var(--color-muted)" strokeDasharray="2 3"/>}
        <text x={x(time)} y={tickY + row * rowPitch} textAnchor="middle" fontSize={compact && curves.length > 1 ? 13 : 12}>{time}</text>
      </g>)}
      <text x="300" y={axisTitleY} textAnchor="middle" fontSize="13">{compact ? "Days of follow-up" : `Time since follow-up began (${unit})`}</text>
      <text x="55" y="25" fontSize="13">{compact ? "Patients still alive" : "Estimated percentage still alive"}</text>
    </svg>
    {compact && curves.length > 1 ? <div className="survival-legend">
      {[...curves].sort((a, b) => a.group.localeCompare(b.group)).map(curve => <span key={curve.group}>
        <span className={curve.group === "higher model risk" ? "higher-score-line" : "lower-score-line"} aria-hidden="true" />
        {curve.group === "higher model risk" ? "Higher scores" : "Lower scores"} ({curve.count})
      </span>)}
    </div> : !compact && <ul>{curves.map(curve => <li key={curve.group} style={{color: curve.group === "higher model risk" ? "var(--color-accent)" : "var(--color-ink-2)"}}>
      {curve.group === "higher model risk" ? "Higher scores" : "Lower scores"} · {curve.count} {curve.count === 1 ? "patient" : "patients"}, {curve.events} recorded {curve.events === 1 ? "death" : "deaths"}
    </li>)}</ul>}
    {!compact && <p>A drop marks one or more recorded deaths.{!denseTimes && ' The dotted lines show when they happened.'}</p>}

  </>;
}
