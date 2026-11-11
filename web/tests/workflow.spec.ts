import { test, expect } from "@playwright/test";
test("select one real patient and progressively render QC before completion", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("3 available patients")).toBeVisible();
  await page.getByLabel("Select all patients").uncheck();
  await expect(
    page.getByRole("button", { name: "Run analysis" }),
  ).toBeDisabled();
  await page.getByLabel("Select LUNG1-001", { exact: true }).check();
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(
    page.getByText("Check 1 selected patients with real DICOM QC."),
  ).toBeVisible();
  await expect(page.getByText("QC · LUNG1-001", { exact: true })).toBeVisible();
  await expect(page.getByText("✓ Passed")).toHaveCount(3, { timeout: 30000 });
  await expect(page.getByText("QC complete.", { exact: false })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Scan quality" }),
  ).toBeVisible();
});
