type Concordance = {
  c_index: number | null;
  evaluated_count: number;
  unavailable_reason?: string | null;
  uncertainty?: { interval?: number[] | null };
};

export function evaluationFinding(evaluation: Concordance): string {
  const { c_index, evaluated_count } = evaluation;
  if (c_index == null) {
    const finding = "The model’s risk rankings couldn’t be compared with observed survival.";
    return evaluation.unavailable_reason ? `${finding} ${evaluation.unavailable_reason}` : finding;
  }

  // Two evaluated patients and a defined C-index establish exactly one comparable pair.
  if (evaluated_count === 2 && c_index === 0) {
    return "In the one comparable pair, the patient with the higher model score had longer observed survival.";
  }
  if (evaluated_count === 2 && c_index === 1) {
    return "In the one comparable pair, the patient with the higher model score had shorter observed survival.";
  }
  if (evaluated_count === 2 && c_index === 0.5) {
    return "In the one comparable pair, both patients received the same model score.";
  }
  const interval = evaluation.uncertainty?.interval;
  if (interval && interval[0] > 0.5) return "Higher model scores generally went with shorter observed survival.";
  if (interval && interval[1] < 0.5) return "Higher model scores generally went with longer observed survival.";
  return "These results don’t clearly show whether higher model scores went with shorter survival.";
}

export function survivalCurveFinding(curves: readonly { group: string }[]): string {
  if (curves.length === 1) {
    return `Only one model-risk group had usable outcomes, so the chart shows the ${curves[0].group} group.`;
  }
  if (curves.length === 0) return "No usable recorded outcomes were available to draw a survival curve.";
  return "The chart shows observed survival for both model-risk groups.";
}

export function riskFinding(patientId: string, percentile?: number | null): string {
  if (percentile == null) return `The model scored ${patientId}. A reference percentile is unavailable.`;
  return `${patientId} scored as high as or higher than about ${Math.round(percentile)}% of the patients the model learned from.`;
}
