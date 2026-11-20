import { test, expect } from '@playwright/test';

test('switching runs keeps one survival model section', async ({ page }) => {
  await page.goto('/workspace?example=completed');
  const modelSections = page.locator('details.prototype-results');
  await expect(modelSections).toHaveCount(1);
  await page.getByText('Run history', { exact: true }).click();
  for (const name of ['Failure example', 'Completed example', 'Failure example']) {
    await page.getByRole('button', { name, exact: true }).click();
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
    await expect(modelSections).toHaveCount(1);
  }
});

test('View Runs shows the completed example immediately, including after refresh', async ({page}) => {
  const artifactRequests: string[] = [];
  await page.route('**/examples/files/**', route => {
    artifactRequests.push(route.request().url());
    return route.abort();
  });
  await page.route('**/examples/curated-success.json', route => route.abort());
  await page.goto('/workspace');
  for (const visit of [0, 1]) {
    if (visit) await page.reload();
    await page.getByRole('button', {name:'View Runs', exact:true}).click();
    await expect(page.getByRole('heading', {name:'Completed example', exact:true})).toBeVisible({timeout:2000});
    await expect(page.getByRole('navigation', {name:'Run sections'})).toBeVisible();
    await expect(page.getByText('Loading example…', {exact:true})).toBeHidden();
  }
  expect(artifactRequests).toEqual([]);
});

test('landing links preserve Back and open the completed demo with the standard navigation', async ({page}) => {
  await page.goto('/');
  await page.getByRole('link', {name:'Run your own analysis', exact:true}).click();
  await expect(page).toHaveURL(/\/workspace$/);
  await page.goBack();
  await expect(page.getByRole('heading', {name:'From CT scans to tumor features.'})).toBeVisible();

  await page.getByRole('link', {name:'View demo run', exact:true}).first().click();
  await expect(page.getByRole('heading', {name:'Completed example', exact:true})).toBeVisible();
  const navigation = page.getByRole('navigation', {name:'Main navigation'});
  await navigation.getByRole('button', {name:'Patients', exact:true}).click();
  await expect(page.getByRole('heading', {name:'Patient library', exact:true})).toBeVisible();
  await expect(page).toHaveURL(/\/workspace$/);
  await page.goBack();
  await expect(page.getByRole('heading', {name:'From CT scans to tumor features.'})).toBeVisible();
});

test('curated execution is immediately inspectable without launching a visitor run', async ({page}) => {
  let launches = 0;
  await page.route('**/api/runs**', async route => { launches++; await route.abort(); });
  await page.goto('/workspace');
  await page.getByRole('button', {name:'View Runs', exact:true}).click();
  await expect(page.getByRole('heading', {name:'Completed example', exact:true})).toBeVisible({timeout:30000});
  const history = page.locator('.run-history:has(+ .saved-run) > details.run-picker');
  const historyTitle = history.locator('summary');
  const historyTable = history.getByRole('table', {name:'Run history'});
  await expect(historyTitle).toHaveText('Run history');
  await expect(history).toHaveJSProperty('open', false);
  await expect(history).toHaveCSS('border-top-width', '0px');
  await expect(historyTable).toBeHidden();
  await historyTitle.click();
  await expect(historyTable.getByRole('button')).toHaveCount(2);
  await historyTitle.click();
  await expect(historyTable).toBeHidden();
  await historyTitle.click();
  await expect(page.getByRole('heading', {name:'View Runs', exact:true})).toHaveCount(0);
  await expect(history.getByRole('button', {name:'Completed example', pressed:true})).toBeVisible();
  await expect(history.getByRole('button', {name:'Failure example'})).toBeVisible();
  await expect(page.getByText('82 patients. Tumor masks and 72 radiomic features per patient.', {exact:true})).toBeVisible();
  const jumpLinks = page.locator('.example-run-heading + nav');
  await expect(jumpLinks.getByRole('link')).toHaveText(['Scans', 'Measurements', 'Model evaluation']);
  await expect(page.getByRole('link', {name:'View run record'})).toHaveCount(0);
  await expect(page.getByRole('region', {name:'Saved run results'})).toBeVisible();
  const results = page.getByRole('region', {name:'Saved run results'});
  await expect(results.getByRole('region', {name:'Radiomic features'})).toBeVisible();
  const prototype = results.locator('#prototype-model');
  await expect(prototype).toHaveJSProperty('open', false);
  await expect(prototype.getByText('Beta', {exact:true})).toBeVisible();
  await prototype.getByText('Survival model Beta', {exact:true}).click();
  await expect(prototype.getByText(/risk rankings may be inaccurate/)).toBeVisible();
  const scoring = results.getByRole('region', {name:'Frozen model risk scores'});
  const evaluation = scoring.getByRole('region', {name:'What happened to the patients you selected'});
  await evaluation.getByText('How to read this result', {exact:true}).click();
  await expect(evaluation.getByText(/82 patients with usable records/).first()).toBeVisible();
  await expect(evaluation.getByText(/C-index 0\.606/).first()).toBeVisible();
  const scoreTable = scoring.getByRole('table', {name:'Patient risk scores', includeHidden:true});
  await expect(scoreTable).toBeHidden();
  await scoring.locator(':scope > details > summary').click();
  await expect(scoreTable).toBeVisible();
  await expect(scoreTable.locator('tbody tr')).toHaveCount(82);
  await expect(page.getByText('Not a medical device or medical advice.', {exact:false})).toBeVisible();
  const masks = page.getByRole('region', {name:'Tumor masks'});
  await masks.locator('summary').first().click();
  await masks.getByText('View tumor volumes', {exact:true}).click();
  const volumeTable = masks.locator('table.result-list-table');
  await expect(volumeTable).toBeVisible();
  await expect(historyTable.getByRole('columnheader')).toHaveCount(2);
  expect((await historyTable.boundingBox())?.x).toBe((await volumeTable.boundingBox())?.x);
  await expect(masks.getByText('82 passed')).toBeVisible();
  const firstMask = masks.getByRole('article').filter({hasText:'LUNG1-002'});
  await firstMask.getByRole('img').hover();
  await expect(firstMask.getByRole('tooltip').getByText('Tumor volume: 368.707 cm³', {exact:true})).toBeVisible();
  const overlay = firstMask.getByRole('img', {name:'LUNG1-002 tumor mask overlay on middle tumor-bearing CT slice'});
  await expect(overlay).toBeVisible();
  await expect.poll(() => overlay.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
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
  await expect(chart).toBeVisible();
  await expect(features.getByText(/original_firstorder_/)).toHaveCount(0);
  await features.getByRole('button', {name:'Inspect LUNG1-009',exact:true}).click();
  await expect(features.getByRole('heading', {name:'LUNG1-009 feature details'})).toBeVisible();
  await page.locator('summary').getByText('Run events', {exact:true}).click();
  const timeline = page.locator('.timeline .event');
  await expect(timeline).toHaveCount(662);
  await expect(timeline.first()).toContainText('plan');
  await expect(timeline.last()).toContainText('done');
  expect(launches).toBe(0);
});

test('failure fixture discloses named exclusions and recorded approval without visitor capabilities', async ({page}) => {
  const controls: string[] = [];
  await page.route('**/api/runs**', async route => { controls.push(route.request().url()); await route.abort(); });
  await page.goto('/workspace');
  await page.getByRole('button', {name:'View Runs', exact:true}).click();
  await page.getByText('Run history', { exact: true }).click();
  await page.getByRole('button',{name:'Failure example',exact:true}).click();
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
    expect(overlays.length).toBe(kind === 'success' ? 82 : 2);
    for (const overlay of overlays) {
      expect(overlay.file).toMatch(/^[a-f0-9]{64}\.png$/);
      expect(overlay.data_base64).toBeUndefined();
    }
    const image = await page.request.get(`/examples/files/${overlays[0].file}`);
    expect(image.ok()).toBeTruthy();
    expect((await image.body()).subarray(0,8)).toEqual(Buffer.from([137,80,78,71,13,10,26,10]));
  }
});
