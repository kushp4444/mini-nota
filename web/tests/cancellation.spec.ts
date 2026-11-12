import { test, expect, BrowserContext } from '@playwright/test';

// Explicit synthetic boundary fixture; does not claim measured imaging output.
async function fixture(context: BrowserContext, loseResponse = false) {
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
  await context.route("**/api/runs/launch-context", r => r.fulfill({json:{worker_context:"synthetic-worker"}}));
  const requests = new Map<string,string>();
  await context.route('**/api/runs', r => {
    const nonce = r.request().postDataJSON().launch_nonce;
    let id = requests.get(nonce);
    if (!id) {id = `cancel-fixture-${++launches}`;requests.set(nonce,id);}
    if (loseResponse) {loseResponse=false;return r.abort('connectionreset');}
    return r.fulfill({status:201,json:{id,secret:'secret',status:'running'}});
  });
  const canceled = new Set<string>();
  await context.route('**/api/runs/*/event-page?*', r => {
    const id = new URL(r.request().url()).pathname.split('/').at(-2)!;
    const after = Number(new URL(r.request().url()).searchParams.get('after'));
    const events = [result(id), ...(canceled.has(id) ? [event(id,2,'done',{status:'canceled',reason:'Canceled by visitor'})] : [])];
    return r.fulfill({json:{id,status:canceled.has(id)?'canceled':'running',events:events.filter(e=>e.sequence>after),next_sequence:events.at(-1)!.sequence,last_sequence:events.at(-1)!.sequence}});
  });
  await context.route('**/api/runs/*/cancel', r => {
    cancellations++;
    canceled.add(new URL(r.request().url()).pathname.split("/").at(-2)!);
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
  await other.getByRole('button',{name:'Patients',exact:true}).click();
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
  await expect.poll(api.launches).toBe(2);
  await page.getByRole('button',{name:'History',exact:true}).click();
  await expect(page.getByRole('button',{name:/Open run cancel-fixture-1/})).toBeVisible();
});

test('simultaneous starts from two tabs create only one run and reload keeps the lock', async ({context,page}) => {
  const api = await fixture(context);
  const other = await context.newPage();
  await Promise.all([page.goto('/'), other.goto('/')]);
  await expect(page.getByRole('button',{name:'Run analysis'})).toBeEnabled();
  await expect(other.getByRole('button',{name:'Run analysis'})).toBeEnabled();
  await Promise.all([
    page.getByRole('button',{name:'Run analysis'}).click({force:true}),
    other.getByRole('button',{name:'Run analysis'}).click({force:true}),
  ]);
  await expect.poll(api.launches).toBe(1);
  await page.reload();
  await page.getByRole('button',{name:'Patients',exact:true}).click();
  await expect(page.getByRole('button',{name:'Run analysis'})).toBeDisabled();
  expect(api.launches()).toBe(1);
});


test('lost creation response reloads the same launch and can cancel it without duplicate work',async ({context,page})=>{
 const api=await fixture(context,true);
 await page.goto('/'); await page.getByRole('button',{name:'Run analysis'}).click();
 await expect(page.getByRole('button',{name:'Retry launch recovery'})).toBeVisible();
 expect(api.launches()).toBe(1);
 await page.reload();
 await expect(page.getByText('Synthetic verified grid')).toBeVisible();
 expect(api.launches()).toBe(1);
 await page.getByRole('button',{name:'Cancel run',exact:true}).click();
 await page.getByRole('button',{name:'Confirm cancellation'}).click();
 await expect(page.getByText('Saved in this browser',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Patients',exact:true}).click();
 await expect(page.getByRole('button',{name:'Run analysis'})).toBeEnabled();
});

test('a lost launch stays occupied until acknowledged interruption and requires explicit new Run',async ({context,page})=>{
 const api=await fixture(context,true);
 await page.goto('/'); await page.getByRole('button',{name:'Run analysis'}).click();
 await expect(page.getByRole('button',{name:'Retry launch recovery'})).toBeVisible();
 let acknowledged=false;
 const recover=async (r: import('@playwright/test').Route)=>r.fulfill(acknowledged
   ? {status:409,json:{detail:{code:'launch_interrupted',message:'Earlier engine work stopped. Start a new run for interrupted computation.'}}}
   : {status:503,json:{detail:'Cannot confirm earlier launch has stopped'}});
 await context.route('**/api/runs',recover);
 await page.reload();
 await expect(page.getByRole('button',{name:'Retry launch recovery'})).toBeVisible();
 await page.getByRole('button',{name:'Patients',exact:true}).click();
 await expect(page.getByRole('button',{name:'Run analysis'})).toBeDisabled();
 expect(api.launches()).toBe(1);
 acknowledged=true; await page.getByRole('button',{name:'Retry launch recovery'}).click();
 await expect(page.getByText(/Start a new run for interrupted computation/)).toBeVisible();
 await page.getByRole('button',{name:'Patients',exact:true}).click();
 await expect(page.getByRole('button',{name:'Run analysis'})).toBeEnabled();
 expect(api.launches()).toBe(1);
 await context.unroute('**/api/runs',recover);
 await page.getByRole('button',{name:'Run analysis'}).click();
 await expect.poll(api.launches).toBe(2);
});
