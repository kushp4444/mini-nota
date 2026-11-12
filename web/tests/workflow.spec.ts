import { test, expect } from "@playwright/test";
test("select one real patient and render verified mask after QC", async ({
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
    page.getByText("Check 1 selected patients with real DICOM QC, construct verified tumor masks, then extract radiomic features for passing patients."),
  ).toBeVisible();
  await expect(page.getByText("QC · LUNG1-001", { exact: true })).toBeVisible();
  await expect(page.getByText("✓ Passed")).toHaveCount(3, { timeout: 30000 });
  await expect(page.getByText("QC, masks and feature extraction complete:", { exact: false })).toBeVisible({timeout:30000});
  await expect(
    page.getByRole("heading", { name: "Scan quality" }),
  ).toBeVisible();
});

// The configured preview uses the real local LUNG1-001 source, not synthetic measurements.
test("mask overlay and physical measurements arrive as retained result bytes", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("3 available patients")).toBeVisible();
  await page.getByLabel("Select all patients").uncheck();
  await page.getByLabel("Select LUNG1-001", { exact: true }).check();
  await page.getByRole("button", {name:"Run analysis"}).click();
  const masks = page.getByLabel("Tumor masks", {exact:true});
  await expect(masks.getByText("56,637", {exact:true})).toBeVisible({timeout:30000});
  await expect(masks.getByText("162.04 cm³", {exact:true})).toBeVisible();
  const overlay = masks.getByRole("img", {name:"LUNG1-001 tumor mask overlay on middle tumor-bearing CT slice"});
  await expect(overlay).toBeVisible();
  await expect(overlay).toHaveAttribute("src", /^data:image\/png;base64,/);
  await expect(page.getByText("1 / 1 checked", {exact:false})).toBeVisible();
});

test("real features arrive progressively with patient detail and a portable CSV", async ({page}) => {
  await page.goto('/');
  await expect(page.getByText('3 available patients')).toBeVisible();
  await page.getByLabel('Select all patients').uncheck();
  await page.getByLabel('Select LUNG1-001', {exact:true}).check();
  await page.getByRole('button', {name:'Run analysis'}).click();
  const features = page.getByLabel('Radiomic features', {exact:true});
  await expect(features.getByText('1 feature rows ready', {exact:true})).toBeVisible({timeout:60000});
  await expect(features.getByRole('table', {name:'Feature measurements'})).toBeVisible();
  await features.getByRole('button', {name:'Inspect LUNG1-001'}).click();
  await expect(features.getByRole('heading', {name:'LUNG1-001 feature details'})).toBeVisible();
  await expect(features.getByText('original_shape_VoxelVolume', {exact:true})).toHaveCount(2);
  await expect(features.getByRole('link', {name:'Download LUNG1-001 features CSV'})).toHaveAttribute('href', /^data:text\/csv;base64,/);
  await expect(page.getByLabel('Tumor masks', {exact:true}).getByRole('img')).toBeVisible();
});
