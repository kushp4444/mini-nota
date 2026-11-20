import { test, expect } from '@playwright/test';

test('full held-out library keeps Run visible and the benchmark near the cohort',async({page})=>{
  await page.setViewportSize({width:1600,height:1000});
  await page.goto('/workspace');
  await expect(page.getByText('82 frozen held-out patients')).toBeVisible();
  await expect(page.getByText(/The beta survival model uses those features/)).toBeVisible();
  await expect(page.getByRole('button',{name:'Run analysis'})).toBeInViewport();
  await page.getByRole('button',{name:'Analysis',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Start an analysis'})).toBeVisible();
  const beta = page.locator('#prototype-model');
  const benchmark = beta.getByLabel('How the model did on its test group',{exact:true});
  await expect(benchmark).toBeHidden();
  expect((await beta.locator('summary').first().boundingBox())!.y).toBeLessThan(850);
  await beta.locator('summary').first().click();
  await expect(benchmark.getByText(/C-index 0\.606/)).toBeVisible();
  await expect(page.getByText('Waiting for mask construction after scan checks…')).toHaveCount(0);
  await page.getByRole('button',{name:'Go to Patients',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Patient library',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Run analysis'})).toBeEnabled();
});

test('saved examples present scan checks and overlays before optional structured audit details',async({page})=>{
  await page.goto('/workspace');
  await page.getByRole('button', {name:'View Runs', exact:true}).click();
  await page.getByText('Run history', { exact: true }).click();
  await page.getByRole('button',{name:'Failure example'}).click();
  const saved=page.getByLabel('Saved run results');
  await expect(saved.getByRole('heading',{name:'Scan quality',exact:true})).toBeVisible();
  await saved.getByLabel('Tumor masks',{exact:true}).locator('summary').first().click();
  await expect(saved.getByLabel('Tumor masks',{exact:true}).getByRole('img').first()).toBeVisible();
  await expect(saved.getByText('LUNG1-015: excluded by QC', {exact:false}).first()).toBeVisible();
  await expect(saved.locator('pre:visible')).toHaveCount(0);
  await saved.getByText('Structured stage details',{exact:true}).click();
  await expect(saved.locator('pre:visible').first()).toBeVisible();
});
