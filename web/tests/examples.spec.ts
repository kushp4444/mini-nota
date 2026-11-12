import { test, expect } from '@playwright/test';

test('curated execution is immediately inspectable without launching a visitor run', async ({page}) => {
  let launches = 0;
  await page.route('**/api/runs**', async route => { launches++; await route.abort(); });
  await page.goto('/');
  await page.getByRole('button', {name:'View completed example', exact:true}).click();
  await expect(page.getByText('Curated success · actual execution', {exact:true})).toBeVisible();
  await expect(page.getByRole('region', {name:'Saved run results'})).toBeVisible();
  await expect(page.getByRole('table', {name:'Patient risk scores'})).toBeVisible();
  await expect(page.getByText('Not a medical device or medical advice.', {exact:false})).toBeVisible();
  await expect(page.getByRole('img', {name:'LUNG1-002 overlay'})).toBeVisible();
  await page.getByRole('button', {name:'Inspect LUNG1-009',exact:true}).click();
  await expect(page.getByRole('heading', {name:'LUNG1-009 feature details'})).toBeVisible();
  const timeline = page.locator('.timeline .event');
  await expect(timeline.first()).toContainText('plan');
  await expect(timeline.last()).toContainText('done');
  expect(launches).toBe(0);
  await page.getByRole('button',{name:'History',exact:true}).click();
  await expect(page.getByText('No saved terminal runs', {exact:true})).toBeVisible();
});

test('failure fixture discloses named exclusions and recorded approval without visitor capabilities', async ({page}) => {
  const controls: string[] = [];
  await page.route('**/api/runs**', async route => { controls.push(route.request().url()); await route.abort(); });
  await page.goto('/');
  await page.getByRole('button',{name:'View failure example',exact:true}).click();
  await expect(page.getByText('Deliberately introduced fixture faults; the live library is unchanged.',{exact:true})).toBeVisible();
  await expect(page.getByRole('region',{name:'Recorded exclusion approval'})).toContainText('2 scoring-eligible patients · 1 evaluation-eligible patients');
  await expect(page.getByRole('region',{name:'Recorded exclusion approval'})).toContainText('LUNG1-015');
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
