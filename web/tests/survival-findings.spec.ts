import { expect, test } from "@playwright/test";
import { evaluationFinding, riskFinding, survivalCurveFinding } from "../lib/survivalFindings";

test("an interval spanning 0.5 makes an above-0.5 estimate inconclusive", () => {
  expect(evaluationFinding({ c_index: 0.61, evaluated_count: 82, uncertainty: { interval: [0.48, 0.71] } }))
    .toMatch(/don’t clearly show whether higher model scores went with shorter survival/);
});

test("an interval above 0.5 supports concordance with shorter observed survival", () => {
  expect(evaluationFinding({ c_index: 0.61, evaluated_count: 82, uncertainty: { interval: [0.53, 0.67] } }))
    .toBe("Higher model scores generally went with shorter observed survival.");
});

test("an interval below 0.5 supports the reverse direction", () => {
  expect(evaluationFinding({ c_index: 0.39, evaluated_count: 82, uncertainty: { interval: [0.33, 0.47] } }))
    .toBe("Higher model scores generally went with longer observed survival.");
});

test("several comparable patients without an interval get an explicitly uncertain finding", () => {
  expect(evaluationFinding({ c_index: 0.68, evaluated_count: 12, uncertainty: { interval: null } }))
    .toBe("These results don’t clearly show whether higher model scores went with shorter survival.");
});

test("an interval touching 0.5 is inconclusive", () => {
  expect(evaluationFinding({ c_index: 0.61, evaluated_count: 82, uncertainty: { interval: [0.5, 0.67] } }))
    .toMatch(/don’t clearly show/);
});

test("a single comparable pair describes the observed order against the ranking", () => {
  expect(evaluationFinding({ c_index: 0, evaluated_count: 2 }))
    .toBe("In the one comparable pair, the patient with the higher model score had longer observed survival.");
});

test("an unavailable comparison explains the effect and preserves the recorded reason", () => {
  expect(evaluationFinding({
    c_index: null,
    evaluated_count: 3,
    unavailable_reason: "No comparable outcome pairs (recorded events and follow-up do not permit concordance).",
  })).toContain("No comparable outcome pairs (recorded events and follow-up do not permit concordance).");
});

test("a single group explains why only one survival curve is shown", () => {
  expect(survivalCurveFinding([{ group: "higher model risk" }]))
    .toBe("Only one model-risk group had usable outcomes, so the chart shows the higher model risk group.");
});

test("the percentile compares an individual with the fixed development reference", () => {
  expect(riskFinding("LUNG1-002", 96.084))
    .toBe("LUNG1-002 scored as high as or higher than about 96% of the patients the model learned from.");
});
