import { expect, test, type Locator } from "@playwright/test";

test("scan flags and feature failures remain visible when an interrupted run is reopened", async ({ page }) => {
  const patientIds = ["FIXTURE-FLAGGED", "FIXTURE-PASSED", "FIXTURE-PENDING"];
  const runId = "imaging-fixture";
  const results = [
    {
      stage: "qc",
      patient: {
        patient_id: patientIds[0],
        status: "failed",
        values: { anonymized: { passed: false, detail: "Possible identifiers in scan headers" } },
        errors: [{ code: "qc_failed", message: "Scan failed quality checks" }],
      },
    },
    { stage: "qc", patient: { patient_id: patientIds[1], status: "success", values: {}, errors: [] } },
    { stage: "masks", patient: { patient_id: patientIds[1], status: "success", values: { volume_cm3: 12.5 }, errors: [] } },
    {
      stage: "features",
      patient: {
        patient_id: patientIds[1],
        status: "failed",
        values: {},
        errors: [{ code: "processing_failed", message: "Could not calculate texture measurements" }],
      },
    },
  ];
  const events = [
    ...results.map(payload => ({ kind: "tool_result", message: "Imaging fixture result", payload })),
    { kind: "done", message: "Run interrupted", payload: { status: "failed" } },
  ].map((event, index) => ({
    ...event, id: `${runId}:${index + 1}`, run_id: runId, sequence: index + 1, timestamp: "2026-11-12T12:00:00Z",
  }));

  await page.route("**/api/graphql", route => route.fulfill({ json: {
    data: { patients: patientIds.map(id => ({ id, label: "Imaging fixture", fixture: true })) },
  } }));
  await page.route("**/api/runs/launch-context", route => route.fulfill({ json: { worker_context: "imaging-fixture" } }));
  await page.route("**/api/runs", route => route.fulfill({ status: 201, json: { id: runId, secret: "fixture-secret", status: "running" } }));
  await page.route(`**/api/runs/${runId}/event-page?*`, route => {
    const after = Number(new URL(route.request().url()).searchParams.get("after"));
    return route.fulfill({ json: {
      id: runId, status: "failed", events: events.filter(event => event.sequence > after),
      next_sequence: events.length, last_sequence: events.length,
    } });
  });

  async function expectFindings(root: Locator) {
    const checks = root.getByRole("region", { name: "Scan quality" });
    await expect(checks.getByText("1 patient passed scan checks and could continue to mask construction.")).toBeVisible();
    await expect(checks.getByText("2 of 3 patients checked · 1 anonymization flag · 1 without a saved check")).toBeVisible();
    const flagged = checks.getByRole("region", { name: "Patients excluded by scan checks" })
      .getByRole("article").filter({ hasText: patientIds[0] });
    await expect(flagged.getByText("Flagged by anonymization check")).toBeVisible();
    await expect(flagged.getByText("Possible identifiers in scan headers", { exact: false })).toBeVisible();
    await checks.getByText("View details", { exact: true }).click();
    await expect(checks.getByRole("article").filter({ hasText: patientIds[2] })).toContainText("Not checked");

    const masks = root.getByRole("region", { name: "Tumor masks" });
    await expect(masks.getByText("A tumor mask was created from the CT scan.")).toBeVisible();
    await expect(masks.getByText("Tumor volume: 12.5 cm³")).toBeVisible();

    const features = root.getByRole("region", { name: "Radiomic features" });
    await expect(features.getByText("We couldn’t measure the tumors from these scans.")).toBeVisible();
    const failure = features.getByRole("article").filter({ hasText: patientIds[1] });
    await expect(failure.getByText("Could not calculate texture measurements")).toBeVisible();
  }

  await page.goto("/");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByText("Saved in this browser", { exact: true })).toBeVisible();
  await expectFindings(page.locator("body"));

  await page.route("**/api/runs/**", route => route.abort());
  await page.reload();
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: `Open run ${runId}` }).click();
  await expectFindings(page.getByRole("region", { name: "Saved run results" }));
});
