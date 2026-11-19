import { expect, test } from "@playwright/test";

test("all 82 patients can be submitted and a quota rejection gives a retry time", { tag: "@smoke" }, async ({ context, page }) => {
  const patients = Array.from({ length: 82 }, (_, i) => ({
    id: `LUNG1-${String(i + 1).padStart(3, "0")}`, label: "Held-out patient", fixture: false,
  }));
  await context.route("**/api/graphql", route => route.fulfill({ json: { data: { patients } } }));
  await context.route("**/api/runs/launch-context", route => route.fulfill({ json: { worker_context: "quota-test" } }));
  let attempts = 0;
  await context.route("**/api/runs", route => {
    expect(route.request().postDataJSON().patient_ids).toEqual(patients.map(patient => patient.id));
    attempts++;
    return route.fulfill({ status: 429, json: { detail: { code: "launch_quota", retry_at: "2030-01-01T12:00:00Z" } } });
  });

  await page.goto("/workspace");
  await expect(page.getByLabel("Select all patients")).toBeChecked();
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "live run limit" })).toContainText(/live run limit.*try again.*2030/i);
  await expect(page.getByRole("button", { name: "Retry launch recovery" })).toHaveCount(0);
  const secondTab = await context.newPage();
  await secondTab.goto("/workspace");
  await secondTab.reload();
  await secondTab.getByRole("button", { name: "Run analysis" }).click();
  await expect(secondTab.getByRole("alert").filter({ hasText: "live run limit" })).toContainText(/live run limit.*2030/i);
  expect(attempts).toBe(2);
});

test("two tabs recovering the first launch initialize its browser cookie only once", async ({ context, page }) => {
  await context.route("**/api/graphql", route => route.fulfill({ json: { data: {
    patients: [{ id: "LUNG1-001", label: "Held-out patient", fixture: false }],
  } } }));
  let contextRequests = 0;
  let releaseContext!: () => void;
  const contextReady = new Promise<void>(resolve => { releaseContext = resolve; });
  await context.route("**/api/runs/launch-context", async route => {
    contextRequests++;
    await contextReady;
    await route.fulfill({ json: { worker_context: "quota-test" } });
  });
  let launchRequests = 0;
  let releaseLaunches!: () => void;
  const launchesReady = new Promise<void>(resolve => { releaseLaunches = resolve; });
  await context.route("**/api/runs", async route => {
    launchRequests++;
    await launchesReady;
    await route.fulfill({ status: 429, json: { detail: { code: "launch_quota", retry_at: "2030-01-01T12:00:00Z" } } });
  });

  try {
    await page.goto("/workspace");
    await page.getByRole("button", { name: "Run analysis" }).click();
    await expect.poll(() => contextRequests).toBe(1);
    const secondTab = await context.newPage();
    await secondTab.goto("/workspace");
    await expect(secondTab.getByText(/Recovering a pending launch/)).toBeVisible();
    releaseContext();
    await expect.poll(() => launchRequests).toBeGreaterThanOrEqual(2);
    expect(contextRequests).toBe(1);
  } finally {
    releaseContext();
    releaseLaunches();
  }
});
