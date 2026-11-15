type Concordance = {
  c_index: number | null;
  evaluated_count: number;
  event_count?: number;
  unavailable_reason?: string | null;
  uncertainty?: { interval?: number[] | null };
};

export function evaluationFinding(evaluation: Concordance): string {
  const { c_index, evaluated_count } = evaluation;
  if (c_index == null) {
    if (evaluated_count === 0) return "There were no patient records we could use to check the model’s ranking.";
    if (evaluated_count === 1) return "We need at least two patients to check the model’s ranking. Only one had a record we could use.";
    return "The records don’t tell us who lived longer, so we couldn’t check the model’s ranking.";
  }

  // Two evaluated patients and a defined C-index establish exactly one comparable pair.
  if (evaluated_count === 2) {
    if (c_index === 0.5) return "The model gave the same score to the two patients we could compare.";
    if (c_index === 0 || c_index === 1) {
      const direction = c_index === 0 ? "longer" : "shorter";
      if (evaluation.event_count === 2) {
        return `Of the two patients we could compare, the one the model ranked higher lived ${direction}.`;
      }
      if (evaluation.event_count === 1) {
        const ranking = c_index === 0 ? "lower" : "higher";
        return `Of the two patients we could compare, the one the model ranked ${ranking} was the only one with a recorded death.`;
      }
      return "We could compare only two patients.";
    }
  }
  const interval = evaluation.uncertainty?.interval;
  if (interval && interval[0] > 0.5) return "Patients the model ranked higher tended to die sooner.";
  if (interval && interval[1] < 0.5) return "Patients the model ranked higher tended to live longer.";
  return "We can’t tell from these results whether patients the model ranked higher died sooner.";
}

export function survivalCurveFinding(curves: readonly { group: string }[]): string {
  if (curves.length === 1) {
    const otherGroup = curves[0].group === "higher model risk" ? "lower" : "higher";
    return `We only had records for one group. There’s no ${otherGroup}-score group to compare it with.`;
  }
  if (curves.length === 0) return "There weren’t any patient records we could use to draw the chart.";
  return "The chart shows how survival changed over time for patients with higher and lower scores.";
}

export function riskFinding(patientId: string, percentile?: number | null): string {
  if (percentile == null) return `The model scored ${patientId}. A reference percentile is unavailable.`;
  return `${patientId} scored as high as or higher than about ${Math.round(percentile)}% of the patients the model learned from.`;
}
