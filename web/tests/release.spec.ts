import { test, expect } from '@playwright/test';

test('full held-out library keeps Run visible and the benchmark near the cohort',async({page})=>{
  await page.setViewportSize({width:1600,height:1000});
  await page.goto('/');
  await expect(page.getByText('82 available patients')).toBeVisible();
  await expect(page.getByRole('button',{name:'Run analysis'})).toBeInViewport();
  await page.getByRole('button',{name:'Analysis',exact:true}).click();
  const benchmark=page.getByLabel('Full held-out evaluation',{exact:true});
  await expect(benchmark.getByText('0.606',{exact:true})).toBeVisible();
  expect((await benchmark.boundingBox())!.y).toBeLessThan(850);
  await expect(page.getByText('Waiting for mask construction after scan checks…')).toHaveCount(0);
});

test('saved examples present scan checks and overlays before optional structured audit details',async({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:'View failure example'}).click();
  const saved=page.getByLabel('Saved run results');
  await expect(saved.getByRole('heading',{name:'Scan quality',exact:true})).toBeVisible();
  await expect(saved.getByLabel('Tumor masks',{exact:true}).getByRole('img').first()).toBeVisible();
  await expect(saved.getByText('LUNG1-015: excluded by QC', {exact:false}).first()).toBeVisible();
  await expect(saved.locator('pre:visible')).toHaveCount(0);
  await saved.getByText('Structured stage details',{exact:true}).click();
  await expect(saved.locator('pre:visible').first()).toBeVisible();
});
