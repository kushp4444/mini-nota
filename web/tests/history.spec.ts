import { test, expect, Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
// Explicit synthetic API fixture: tests local history, not measured imaging results.
async function fixture(page: Page, status = "completed") {
  await page.route("**/api/graphql", (route) =>
    route.fulfill({
      json: {
        data: {
          patients: [
            {
              id: "LUNG1-001",
              label: "Synthetic history fixture",
              fixture: true,
            },
          ],
        },
      },
    }),
  );
  let count = 0;
  await page.route("**/api/runs", (route) =>
    route.fulfill({
      status: 201,
      json: {
        id: `fixture-${++count}`,
        secret: "fixture-secret",
        status: "running",
      },
    }),
  );
  await page.route("**/api/runs/*/events", (route) => {
    const id = route.request().url().split("/").at(-2)!;
    const events = [
      {
        kind: "tool_result",
        message: "Synthetic mask result",
        payload: {
          stage: "masks",
          patient: {
            patient_id: "LUNG1-001",
            status: "success",
            values: { volume_cm3: 12.5 },
            errors: [],
            artifacts: [
              {
                role: "overlay",
                media_type: "image/png",
                data_base64: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==",
              },
            ],
          },
        },
      },
      ...(status === "failed"
        ? [
            {
              kind: "tool_call",
              message: "Synthetic feature extraction started",
              payload: { stage: "features" },
            },
          ]
        : []),
      {
        kind: "done",
        message:
          status === "failed"
            ? "Synthetic engine failure"
            : status === "canceled"
              ? "Synthetic canceled by browser visitor"
              : "Synthetic run complete",
        payload: { status },
      },
    ].map((event, i) => ({
      ...event,
      id: `${id}:${i + 1}`,
      run_id: id,
      sequence: i + 1,
      timestamp: "2026-11-11T12:00:00Z",
    }));
    return route.fulfill({
      contentType: "text/event-stream",
      body: events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join(""),
    });
  });
}
for (const outcome of ["completed", "failed", "canceled"]) {
test(`${outcome} results and PNG bytes survive reload and a new run without server access`, async ({
  page,
}) => {
  await fixture(page, outcome);
  await page.goto("/");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(
    page.getByText("Saved in this browser", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: /Open run fixture-1/ }).click();
  await expect(page.getByText("12.5", { exact: false })).toBeVisible();
  await expect(page.getByRole("img", { name: /overlay/ })).toBeVisible();
  await expect(page.getByRole("img", { name: /overlay/ })).toHaveJSProperty(
    "naturalWidth",
    1,
  );
  await expect(page.getByText("Not run — no result saved")).toHaveCount(outcome === "failed" ? 2 : 3);
  await page.getByRole("button", { name: "Patients", exact: true }).click();
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(
    page.getByText("Saved in this browser", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "History", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Open run fixture-/ }),
  ).toHaveCount(2);
  const replayRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/runs"))
      replayRequests.push(request.url());
  });
  await page.route("**/api/runs/**", (r) => r.abort());
  await page.reload();
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: /Open run fixture-1/ }).click();
  await expect(page.getByRole("img", { name: /overlay/ })).toHaveJSProperty(
    "naturalWidth",
    1,
  );
  expect(replayRequests).toHaveLength(0);
});
}
test("failed runs retain available results and name unfinished stages", async ({
  page,
}) => {
  await fixture(page, "failed");
  await page.goto("/");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(
    page.getByText("Saved in this browser", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: /Open run fixture-1/ }).click();
  const results = page.getByRole("region", { name: "Saved run results" });
  await expect(
    results.getByText("Synthetic engine failure", { exact: true }),
  ).toBeVisible();
  await expect(
    results.getByRole("heading", { name: "Saved run · failed" }),
  ).toBeVisible();
  await expect(results.getByText("Not run — no result saved")).toHaveCount(2);
  await expect(results.getByText("Unfinished — no result saved")).toBeVisible();
  await expect(results.getByRole("img")).toHaveCount(1);
  await expect(page.locator(".timeline .event").first()).toContainText(
    "Synthetic mask result",
  );
  await expect(page.locator(".timeline .event").last()).toContainText(
    "Synthetic engine failure",
  );
});
test("unavailable browser storage is explained without claiming a save", async ({
  page,
}) => {
  await page.addInitScript(() =>
    Object.defineProperty(window, "indexedDB", { get: () => undefined }),
  );
  await fixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /Browser history|Browser storage|Missing artifact/ })).toContainText(
    "Browser history is unavailable",
  );
  await page.getByRole("button", { name: "History", exact: true }).click();
  await expect(page.getByRole("button", { name: /Open run/ })).toHaveCount(0);
  await expect(
    page.getByText("Saved in this browser", { exact: true }),
  ).toHaveCount(0);
});
test("quota failures are visible and never reported as saved", async ({
  page,
}) => {
  // Fault injection at the browser storage boundary, not an application collaborator.
  await page.addInitScript(() => {
    IDBObjectStore.prototype.put = function () {
      throw new DOMException("Synthetic full quota", "QuotaExceededError");
    };
  });
  await fixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /Browser history|Browser storage|Missing artifact/ })).toContainText(
    "Browser storage is full",
  );
  await expect(page.locator(".run-summary")).toContainText("completed");
  await expect(
    page.getByText("Saved in this browser", { exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "History", exact: true }).click();
  await expect(page.getByRole("button", { name: /Open run/ })).toHaveCount(0);
});
test("canceled terminal records are readable without inventing later results", async ({
  page,
}) => {
  await fixture(page, "canceled");
  await page.goto("/");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(
    page.getByText("Saved in this browser", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: /Open run fixture-1/ }).click();
  await expect(
    page.getByRole("heading", { name: "Saved run · canceled" }),
  ).toBeVisible();
  await expect(page.getByText("Not run — no result saved")).toHaveCount(3);
});
test("temporary artifact bytes remain local after the application artifact disappears", async ({
  page,
}) => {
  await fixture(page);
  const source = "/api/runs/fixture-1/artifacts/overlay";
  await page.route("**/api/runs/*/events", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: [
        {
          id: "fixture-1:1",
          run_id: "fixture-1",
          sequence: 1,
          timestamp: "2026-11-11T12:00:00Z",
          kind: "tool_result",
          message: "Synthetic temporary overlay",
          payload: {
            stage: "masks",
            patient: {
              patient_id: "LUNG1-001",
              status: "success",
              values: { volume_cm3: 12.5 },
              errors: [],
              artifacts: [
                { role: "overlay", media_type: "image/svg+xml", url: source },
              ],
            },
          },
        },
        {
          id: "fixture-1:2",
          run_id: "fixture-1",
          sequence: 2,
          timestamp: "2026-11-11T12:00:01Z",
          kind: "done",
          message: "Synthetic complete",
          payload: { status: "completed" },
        },
      ]
        .map((e) => `data: ${JSON.stringify(e)}\n\n`)
        .join(""),
    }),
  );
  await page.route(`**${source}`, (route) =>
    route.fulfill({
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12"><rect width="12" height="12" fill="blue"/></svg>',
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(
    page.getByText("Saved in this browser", { exact: true }),
  ).toBeVisible();
  await page.route(`**${source}`, (route) =>
    route.fulfill({ status: 410, body: "Temporary file removed" }),
  );
  await page.reload();
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: /Open run fixture-1/ }).click();
  await expect(page.getByRole("img", { name: /overlay/ })).toHaveJSProperty(
    "naturalWidth",
    12,
  );
});
test("missing artifacts retain actual numerical results and a named warning", async ({
  page,
}) => {
  await fixture(page);
  await page.route("**/api/runs/*/events", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: [
        {
          id: "fixture-1:1",
          run_id: "fixture-1",
          sequence: 1,
          timestamp: "2026-11-11T12:00:00Z",
          kind: "tool_result",
          message: "Synthetic missing overlay",
          payload: {
            stage: "masks",
            patient: {
              patient_id: "LUNG1-001",
              status: "success",
              values: { volume_cm3: 12.5 },
              errors: [],
              artifacts: [
                {
                  role: "overlay",
                  media_type: "image/png",
                  path: "/removed/overlay.png",
                },
              ],
            },
          },
        },
        {
          id: "fixture-1:2",
          run_id: "fixture-1",
          sequence: 2,
          timestamp: "2026-11-11T12:00:01Z",
          kind: "done",
          message: "Synthetic complete",
          payload: { status: "completed" },
        },
      ]
        .map((e) => `data: ${JSON.stringify(e)}\n\n`)
        .join(""),
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(
    page.getByText("Saved in this browser", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: /Open run fixture-1/ }).click();
  await expect(page.getByRole("alert").filter({ hasText: /Browser history|Browser storage|Missing artifact/ })).toContainText(
    "Missing artifact: overlay",
  );
  await expect(page.getByText("12.5", { exact: false })).toBeVisible();
  await expect(page.getByRole("region", { name: "Saved run results" }).getByRole("img")).toHaveCount(0);
});

test("feature and survival stage values and data artifacts remain inspectable after reload", async ({ page }) => {
  await fixture(page);
  await page.route("**/api/runs/*/events", route => route.fulfill({
    contentType: "text/event-stream",
    body: [
      { kind: "tool_result", message: "Synthetic feature result", payload: {
        stage: "features", patient: { patient_id: "LUNG1-001", status: "success", values: { original_shape_Sphericity: 0.72 }, errors: [] },
        artifacts: [{ role: "feature-table", media_type: "text/csv", data_base64: Buffer.from("patient_id,sphericity\nLUNG1-001,0.72\n").toString("base64") }]
      } },
      { kind: "tool_result", message: "Synthetic frozen-model result", payload: {
        stage: "survival", model_version: "synthetic-v1", scores: [{patient_id: "LUNG1-001", risk_percentile: 63.2}], evaluation: {available: false, reason: "No comparable pairs"}
      } },
      { kind: "done", message: "Synthetic complete", payload: {status: "completed"} }
    ].map((event, i) => `data: ${JSON.stringify({...event, id: `fixture-1:${i + 1}`, run_id: "fixture-1", sequence: i + 1, timestamp: "2026-11-11T12:00:00Z"})}\n\n`).join("")
  }));
  await page.goto("/");
  await page.getByRole("button", {name: "Run analysis"}).click();
  await expect(page.getByText("Saved in this browser", {exact: true})).toBeVisible();
  await page.route("**/api/runs/**", route => route.abort());
  await page.reload();
  await page.getByRole("button", {name: "History", exact: true}).click();
  await page.getByRole("button", {name: /Open run fixture-1/}).click();
  const results = page.getByRole("region", {name: "Saved run results"});
  await expect(results.getByText(/original_shape_Sphericity/)).toContainText("0.72");
  await expect(results.getByText(/synthetic-v1/)).toContainText("63.2");
  await expect(results.getByText(/synthetic-v1/)).toContainText("No comparable pairs");
  const download = await Promise.all([
    page.waitForEvent("download"),
    results.getByRole("link", {name: "Open saved feature-table"}).click()
  ]);
  expect(await download[0].failure()).toBeNull();
  expect(await readFile((await download[0].path())!, "utf8")).toBe("patient_id,sphericity\nLUNG1-001,0.72\n");
  await expect(results.getByText("Not run — no result saved")).toHaveCount(2);
});
