// Release harness: run against the real 82-patient catalog, immutable assets and live runner.
import { test, expect } from "@playwright/test";
test("select one real patient and render verified mask after QC", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("82 available patients")).toBeVisible();
  await page.getByLabel("Select all patients").uncheck();
  await expect(
    page.getByRole("button", { name: "Run analysis" }),
  ).toBeDisabled();
  await page.getByLabel("Select LUNG1-002", { exact: true }).check();
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(
    page.getByText("Check 1 selected patients with real DICOM QC, construct verified tumor masks, then extract radiomic features and score eligible held-out patients with the frozen model."),
  ).toBeVisible();
  await expect(page.getByText("QC · LUNG1-002", { exact: true })).toBeVisible();
  const checks = page.getByRole("region", { name: "Scan quality" });
  await expect(checks.getByText("1 patient passed scan checks and could continue to mask construction.")).toBeVisible({ timeout: 30000 });
  await checks.getByText("View details", { exact: true }).click();
  await expect(checks.getByText("✓ Passed")).toHaveCount(3);
  await expect(page.getByText("All four tools complete:", { exact: false })).toBeVisible({timeout:30000});
  await expect(
    page.getByRole("heading", { name: "Scan quality" }),
  ).toBeVisible();
});

// Actual frozen held-out LUNG1-002; no three-patient fixture backend.
test("mask overlay and physical measurements arrive as retained result bytes", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("82 available patients")).toBeVisible();
  await page.getByLabel("Select all patients").uncheck();
  await page.getByLabel("Select LUNG1-002", { exact: true }).check();
  await page.getByRole("button", {name:"Run analysis"}).click();
  const masks = page.getByLabel("Tumor masks", {exact:true});
  await expect(masks.getByText("Tumor volume: 368.707 cm³ · 128,757 tumor voxels")).toBeVisible({timeout:30000});
  const overlay = masks.getByRole("img", {name:"LUNG1-002 tumor mask overlay on middle tumor-bearing CT slice"});
  await expect(overlay).toBeVisible();
  await expect(overlay).toHaveAttribute("src", /^data:image\/png;base64,/);
  await expect(page.getByRole("region", {name:"Scan quality"}).getByText("1 of 1 patients checked")).toBeVisible();
});

test("real features arrive progressively with patient detail and a portable CSV", async ({page}) => {
  await page.goto('/');
  await expect(page.getByText('82 available patients')).toBeVisible();
  await page.getByLabel('Select all patients').uncheck();
  await page.getByLabel('Select LUNG1-002', {exact:true}).check();
  await page.getByRole('button', {name:'Run analysis'}).click();
  const features = page.getByLabel('Radiomic features', {exact:true});
  await expect(features.getByText('We measured the tumors’ shape, CT intensity, and patterns in the scan.')).toBeVisible({timeout:60000});
  await expect(features.getByText('1 patient with measurements · 72 measurements per patient')).toBeVisible();
  await features.getByText('View details', {exact:true}).click();
  await expect(features.getByRole('table', {name:'Feature measurements'})).toBeVisible();
  await features.getByRole('button', {name:'Inspect LUNG1-002'}).click();
  await expect(features.getByRole('heading', {name:'LUNG1-002 feature details'})).toBeVisible();
  await expect(features.getByText('Tumor volume from the mask (mm³)', {exact:true})).toHaveCount(2);
  await expect(features.getByRole('link', {name:'Download LUNG1-002 features CSV'})).toHaveAttribute('href', /^data:text\/csv;base64,/);
  await expect(page.getByLabel('Tumor masks', {exact:true}).getByRole('img')).toBeVisible();
});
