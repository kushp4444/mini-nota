import { test, expect } from '@playwright/test';

test('curated execution is immediately inspectable without launching a visitor run', async ({page}) => {
  let launches = 0;
  await page.route('**/api/runs**', async route => { launches++; await route.abort(); });
  await page.goto('/');
  await page.getByRole('button', {name:'View completed example', exact:true}).click();
  await expect(page.getByText('Completed example', {exact:true})).toBeVisible();
  await expect(page.getByRole('region', {name:'Saved run results'})).toBeVisible();
  const results = page.getByRole('region', {name:'Saved run results'});
  await expect(results.getByText('The higher-ranked patient lived longer.')).toBeVisible();
  const scoring = results.getByRole('region', {name:'Frozen model risk scores'});
  for (const [id, days] of [["LUNG1-002", "155 days"], ["LUNG1-009", "131 days"]]) {
    const patient = scoring.locator(".patient-risk-findings > div").filter({has: page.getByRole("heading", {name: id, exact: true})});
    await expect(patient.getByText(`${days.split(" ")[0]}days to recorded death`, {exact: true})).toBeVisible();
  }
  const scoreTable = scoring.getByRole('table', {name:'Patient risk scores', includeHidden:true});
  await expect(scoreTable).toBeHidden();
  await scoring.locator(':scope > details > summary').click();
  await expect(scoreTable).toBeVisible();
  await expect(page.getByText('Not a medical device or medical advice.', {exact:false})).toBeVisible();
  const masks = page.getByRole('region', {name:'Tumor masks'});
  await masks.locator('summary').first().click();
  await expect(masks.getByText('2 passed')).toBeVisible();
  const firstMask = masks.getByRole('article').filter({hasText:'LUNG1-002'});
  await firstMask.getByRole('img').hover();
  await expect(firstMask.getByRole('tooltip').getByText('Tumor volume: 368.707 cm³', {exact:true})).toBeVisible();
  await expect(firstMask.getByRole('img', {name:'LUNG1-002 tumor mask overlay on middle tumor-bearing CT slice'})).toBeVisible();
  const features = page.getByRole('region', {name:'Radiomic features'});
  await features.getByText('Tumor measurements', {exact:true}).click();
  await expect(features.getByText('Shape, intensity, and texture.')).toBeVisible();
  await expect(features.getByText('72 per patient')).toBeVisible();
  const measurements = features.getByRole('table', {name:'Feature measurements'});
  await expect(measurements).toBeHidden();
  await features.getByRole('button', {name:'View all',exact:true}).click();
  await expect(measurements).toBeVisible();
  await expect(measurements.getByRole('columnheader', {name:'Average CT intensity', exact:true})).toBeVisible();
  await expect(measurements.getByRole('button', {name:'About Average CT intensity'})).toHaveCount(0);
  const intensity = features.locator('dt').filter({hasText:'Average CT intensity'});
  await expect(intensity).toContainText('Normalized intensity');
  await intensity.getByRole('button', { name: 'About Average CT intensity' }).hover();
  await expect(page.getByRole('tooltip')).toContainText('divide by the number of points');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('tooltip')).toBeHidden();
  await intensity.getByRole('button', { name: 'About Average CT intensity' }).focus();
  await expect(page.getByRole('tooltip')).toBeVisible();
  await page.keyboard.press('Escape');
  const chart = results.getByRole('img', {name:'Estimated percentage of patients still alive over time'});
  await expect(chart.getByText('131', {exact:true})).toBeVisible();
  await expect(chart.getByText('155', {exact:true})).toBeVisible();
  await expect(features.getByText(/original_firstorder_/)).toHaveCount(0);
  await expect(results.getByRole('img', {name:'Estimated percentage of patients still alive over time'})).toBeVisible();
  await features.getByRole('button', {name:'Inspect LUNG1-009',exact:true}).click();
  await expect(features.getByRole('heading', {name:'LUNG1-009 feature details'})).toBeVisible();
  await page.locator('summary').getByText('Run events', {exact:true}).click();
  const timeline = page.locator('.timeline .event');
  await expect(timeline.first()).toContainText('plan');
  await expect(timeline.last()).toContainText('done');
  expect(launches).toBe(0);
  await page.getByRole('button',{name:'Examples',exact:true}).first().click();
  await page.getByRole('button',{name:'History',exact:true}).click();
  await expect(page.getByText('No saved terminal runs', {exact:true})).toBeVisible();
});

test('failure fixture discloses named exclusions and recorded approval without visitor capabilities', async ({page}) => {
  const controls: string[] = [];
  await page.route('**/api/runs**', async route => { controls.push(route.request().url()); await route.abort(); });
  await page.goto('/');
  await page.getByRole('button',{name:'View failure example',exact:true}).click();
  await expect(page.getByText('Deliberately introduced fixture faults; the live library is unchanged.',{exact:true})).toBeVisible();
  const checks = page.getByRole('region', {name:'Scan quality'});
  await expect(checks.getByText('2 patients passed scan checks and could continue to mask construction.')).toBeVisible();
  await expect(checks.getByText('3 of 3 patients checked · 1 processing failure')).toBeVisible();
  const failure = checks.getByRole('article').filter({hasText:'LUNG1-015'});
  await expect(failure.getByText('Processing failure')).toBeVisible();
  await expect(failure.getByText('Patient stage processing failed')).toBeVisible();
  await expect(page.getByRole('region',{name:'Recorded exclusion approval'})).toContainText('2 scoring-eligible patients · 1 evaluation-eligible patients');
  await expect(page.getByRole('region',{name:'Recorded exclusion approval'})).toContainText('LUNG1-015');
  await expect(page.getByRole('region',{name:'Recorded exclusion approval'})).toContainText('Approval recorded.');
  await expect(page.getByRole('region',{name:'Recorded exclusion approval'})).toContainText('No recorded outcome; risk scoring remains available');
  await expect(page.getByRole('button',{name:'Approve disclosed cohort and score'})).toHaveCount(0);
  const events = page.locator('.timeline .event');
  const text = await events.allTextContents();
  const gate = text.findIndex(t => t.includes('gate'));
  const approval = text.findIndex(t => t.includes('Anonymous run approval recorded'));
  const scoring = text.findIndex(t => t.includes('Frozen model scoring'));
  expect(gate).toBeGreaterThan(0);
  expect(approval).toBeGreaterThan(gate);
  expect(scoring).toBeGreaterThan(approval);
  await expect(events.last()).toContainText('done');
  expect(controls).toEqual([]);
  expect(await page.evaluate(() => localStorage.getItem('mini-nota-active-run'))).toBeNull();
  for (const kind of ['success','failure']) {
    const asset = await (await page.request.get(`/examples/curated-${kind}.json`)).json();
    const forbidden = ['secret','launch_nonce','worker_context','checkpoint','disclosure_id','signature','token','checkpoint_token','path','url'];
    function inspect(value: any) {
      if (Array.isArray(value)) return value.forEach(inspect);
      if (value && typeof value === 'object') for (const [key, child] of Object.entries(value)) {
        expect(forbidden).not.toContain(key); inspect(child);
      }
    }
    inspect(asset);
    const overlays = asset.events.filter((e:any) => e.payload.stage === 'masks' && e.kind === 'tool_result').flatMap((e:any) => e.payload.patient.artifacts);
    expect(overlays.length).toBe(2);
    for (const overlay of overlays) expect(Buffer.from(overlay.data_base64,'base64').subarray(0,8)).toEqual(Buffer.from([137,80,78,71,13,10,26,10]));
  }
});
