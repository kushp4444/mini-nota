import { expect, test } from "@playwright/test";
import { evaluationFinding, riskFinding, survivalCurveFinding } from "../lib/survivalFindings";

test("an interval spanning 0.5 makes an above-0.5 estimate inconclusive", () => {
  expect(evaluationFinding({ c_index: 0.61, evaluated_count: 82, uncertainty: { interval: [0.48, 0.71] } }))
    .toMatch(/can’t tell from these results whether patients the model ranked higher died sooner/);
});

test("an interval above 0.5 supports concordance with shorter observed survival", () => {
  expect(evaluationFinding({ c_index: 0.61, evaluated_count: 82, uncertainty: { interval: [0.53, 0.67] } }))
    .toBe("Patients the model ranked higher tended to die sooner.");
});

test("an interval below 0.5 supports the reverse direction", () => {
  expect(evaluationFinding({ c_index: 0.39, evaluated_count: 82, uncertainty: { interval: [0.33, 0.47] } }))
    .toBe("Patients the model ranked higher tended to live longer.");
});

test("several comparable patients without an interval get an explicitly uncertain finding", () => {
  expect(evaluationFinding({ c_index: 0.68, evaluated_count: 12, uncertainty: { interval: null } }))
    .toBe("We can’t tell from these results whether patients the model ranked higher died sooner.");
});

test("an interval touching 0.5 is inconclusive", () => {
  expect(evaluationFinding({ c_index: 0.61, evaluated_count: 82, uncertainty: { interval: [0.5, 0.67] } }))
    .toMatch(/can’t tell/);
});

test("a single comparable pair describes the observed order against the ranking", () => {
  expect(evaluationFinding({ c_index: 0, evaluated_count: 2, event_count: 2 }))
    .toBe("Of the two patients we could compare, the one the model ranked higher lived longer.");
});

test("a single pair with an incomplete outcome describes the observed event", () => {
  expect(evaluationFinding({ c_index: 0, evaluated_count: 2, event_count: 1 }))
    .toBe("Of the two patients we could compare, the one the model ranked lower was the only one with a recorded death.");
});

test("an unavailable comparison explains why the ranking could not be checked", () => {
  expect(evaluationFinding({
    c_index: null,
    evaluated_count: 3,
    unavailable_reason: "No comparable outcome pairs (recorded events and follow-up do not permit concordance).",
  })).toMatch(/records don’t tell us who lived longer/);
});

test("a single group explains why only one survival curve is shown", () => {
  expect(survivalCurveFinding([{ group: "higher model risk" }]))
    .toBe("We only had records for one group. There’s no lower-score group to compare it with.");
});

test("the percentile compares an individual with the fixed development reference", () => {
  expect(riskFinding("LUNG1-002", 96.084))
    .toBe("LUNG1-002 scored as high as or higher than about 96% of the patients the model learned from.");
});
