import { test, expect, BrowserContext } from '@playwright/test';

// Explicit synthetic boundary fixture; does not claim measured imaging output.
async function fixture(context: BrowserContext) {
  let launches = 0, cancellations = 0;
  const event = (id: string, sequence: number, kind: string, payload: object) => ({
    id: `${id}:${sequence}`, run_id: id, sequence, kind, payload,
    timestamp: '2026-11-11T12:00:00Z', message: kind === 'done' ? 'Canceled by visitor' : 'Synthetic scan result',
  });
  const result = (id: string) => event(id, 1, 'tool_result', { stage: 'qc', patient: {
    patient_id: 'LUNG1-001', status: 'success', errors: [], artifacts: [],
    values: { geometry: { passed: true, detail: 'Synthetic verified grid' } },
  }});
  await context.route('**/api/graphql', r => r.fulfill({json: { data: { patients: [{id:'LUNG1-001',label:'Synthetic cancel fixture',fixture:true}] } }}));
  await context.route('**/api/runs', r => r.fulfill({status:201,json:{id:`cancel-fixture-${++launches}`,secret:'secret',status:'running'}}));
  await context.route('**/api/runs/*/events', r => {
    const id = r.request().url().split('/').at(-2)!;
    return r.fulfill({contentType:'text/event-stream',body:`data: ${JSON.stringify(result(id))}\n\n`});
  });
  await context.route('**/api/runs/*/cancel', r => {
    cancellations++;
    return r.fulfill({json:{status:'canceled'}});
  });
  await context.route(/\/api\/runs\/cancel-fixture-\d+$/, r => {
    const id = r.request().url().split('/').at(-1)!;
    return r.fulfill({json:{id,status:'canceled',events:[result(id),event(id,2,'done',{status:'canceled',reason:'Canceled by visitor'})]}});
  });
  return { launches: () => launches, cancellations: () => cancellations };
}

test('confirmation dismisses safely; cancellation retains results and enables a fresh run across tabs', async ({context,page,browser}) => {
  const api = await fixture(context);
  await page.goto('/');
  await page.getByRole('button',{name:'Run analysis'}).click();
  await expect(page.getByText('Synthetic verified grid')).toBeVisible();
  const other = await context.newPage();
  await other.goto('/');
  await expect(other.getByRole('button',{name:'Run analysis'})).toBeDisabled();
  expect(api.launches()).toBe(1);
  const independent = await browser.newContext();
  await fixture(independent);
  const independentPage = await independent.newPage();
  await independentPage.goto('/');
  await expect(independentPage.getByRole('button',{name:'Run analysis'})).toBeEnabled();
  await independent.close();
  await page.getByRole('button',{name:'Cancel run',exact:true}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button',{name:'Keep running'}).click();
  expect(api.cancellations()).toBe(0);
  await expect(other.getByRole('button',{name:'Run analysis'})).toBeDisabled();
  await page.getByRole('button',{name:'Cancel run',exact:true}).click();
  await page.getByRole('button',{name:'Confirm cancellation'}).click();
  await expect(page.getByText('Saved in this browser',{exact:true})).toBeVisible();
  expect(api.cancellations()).toBe(1);
  await expect(other.getByRole('button',{name:'Run analysis'})).toBeEnabled();
  await page.getByRole('button',{name:'History',exact:true}).click();
  await page.getByRole('button',{name:/Open run cancel-fixture-1/}).click();
  await expect(page.getByText('Canceled by visitor',{exact:false}).first()).toBeVisible();
  await page.getByRole('button',{name:'Patients',exact:true}).click();
  await page.getByRole('button',{name:'Run analysis'}).click();
  expect(api.launches()).toBe(2);
  await page.getByRole('button',{name:'History',exact:true}).click();
  await expect(page.getByRole('button',{name:/Open run cancel-fixture-1/})).toBeVisible();
});
