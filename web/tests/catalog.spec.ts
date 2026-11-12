import { test, expect } from "@playwright/test";

test("real held-out catalog labels and default selection follow the server", async ({ page }) => {
  // Synthetic transport fixture verifies UI behavior; this is not a measured cohort.
  await page.route("**/api/graphql", async (route) => {
    await route.fulfill({ json: { data: { patients: [
      { id: "LUNG1-101", label: "Public Lung1 · frozen held-out patient", fixture: false },
      { id: "LUNG1-102", label: "Public Lung1 · frozen held-out patient", fixture: false },
    ] } } });
  });
  await page.goto("/");
  await expect(page.getByText("2 frozen held-out patients · excluded from model development", { exact: true })).toBeVisible();
  await expect(page.getByText("DEVELOPMENT FIXTURE", { exact: true })).toHaveCount(0);
  await expect(page.getByText("FROZEN HELD-OUT LIBRARY", { exact: true })).toBeVisible();
  const boxes = page.locator("tbody input[type=checkbox]");
  await expect(boxes).toHaveCount(2);
  await expect(boxes.nth(0)).toBeChecked();
  await expect(boxes.nth(1)).toBeChecked();
  await boxes.nth(0).uncheck();
  await expect(page.getByText("1 selected", { exact: true })).toBeVisible();
});
