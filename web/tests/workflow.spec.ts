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
    page.getByText("Check 1 selected patients with real DICOM QC, then construct verified tumor masks for passing patients."),
  ).toBeVisible();
  await expect(page.getByText("QC · LUNG1-001", { exact: true })).toBeVisible();
  await expect(page.getByText("✓ Passed")).toHaveCount(3, { timeout: 30000 });
  await expect(page.getByText("QC and mask construction complete:", { exact: false })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Scan quality" }),
  ).toBeVisible();
});

// The configured preview uses the real local LUNG1-001 source, not synthetic measurements.
test("mask overlay and physical measurements arrive as retained result bytes", async ({ page }) => {
  await page.goto("/");
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
