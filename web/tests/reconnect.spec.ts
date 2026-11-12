import { test, expect, BrowserContext } from '@playwright/test';
// Synthetic API responses exercise browser persistence/reconnect, not imaging measurements.
const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==';
async function setup(context: BrowserContext) {
  let finished = false, lost = false, stale = false, produced = 1;
  const cursors: number[] = [];
  const events = [
    { kind: 'plan', message: 'Synthetic plan', payload: {} },
    { kind: 'tool_result', message: 'Synthetic mask collected after return', payload: { stage: 'masks', patient: {patient_id: 'LUNG1-001', status: 'success', values: {volume_cm3: 12.5}, errors: [], artifacts: [{role: 'overlay', media_type: 'image/png', data_base64: png}]}} },
    { kind: 'done', message: 'Synthetic completed', payload: {status:'completed'} },
  ].map((e,i) => ({...e,id:`recover:${i+1}`,run_id:'recover',sequence:i+1,timestamp:'2026-11-11T12:00:00Z'}));
  await context.route('**/api/graphql', r => r.fulfill({json:{data:{patients:[{id:'LUNG1-001', label:'Synthetic fixture',fixture:true}]}}}));
  await context.route("**/api/runs/launch-context", r => r.fulfill({json:{worker_context:"synthetic-worker"}}));
  await context.route('**/api/runs',r => r.fulfill({status:201,json:{id:'recover',secret:'opaque-secret',status:'running'}}));
  await context.route('**/api/runs/recover/event-page?*',r => {
    expect(r.request().headers()['authorization']).toBe('Bearer opaque-secret');
    if (lost || stale) return r.fulfill({status:lost?404:403,json:{detail:'Unavailable'}});
    const after = Number(new URL(r.request().url()).searchParams.get('after'));
    cursors.push(after);
    const available = finished ? events : events.slice(0,produced);
    return r.fulfill({json:{id:'recover',status:finished?'completed':'running',events:available.filter(e=>e.sequence>after).slice(0,1),next_sequence:Math.min(after+1,available.length),last_sequence:available.length}});
  });
  return { cursors, mask:()=>{produced=2}, finish:()=>{finished=true}, lose:()=>{lost=true}, stale:()=>{stale=true} };
}
test('closing a tab then returning after completion resumes cursor and retains actual bytes',async ({context,page})=>{
 const server=await setup(context);
 await page.goto('/'); await page.getByRole('button',{name:'Run analysis'}).click();
 await expect(page.locator('.timeline')).toContainText('Synthetic plan');
 await page.close(); server.finish();
 const returned=await context.newPage(); await returned.goto('/');
 await expect(returned.getByText('Saved in this browser',{exact:true})).toBeVisible();
 expect(server.cursors).toContain(1);
 await returned.reload(); await returned.getByRole('button',{name:'History',exact:true}).click();
 await returned.getByRole('button',{name:/Open run recover/}).click();
 await expect(returned.locator('.timeline .event')).toHaveCount(3);
 await expect(returned.getByRole('img',{name:/overlay/})).toHaveJSProperty('naturalWidth',1);
});
for (const outcome of ['lose','stale'] as const) test(`${outcome} runner access produces explained local failure and permits a new run`,async ({context,page})=>{
 const server=await setup(context); await page.goto('/'); await page.getByRole('button',{name:'Run analysis'}).click();
 await expect(page.locator('.timeline')).toContainText('Synthetic plan');
 server[outcome](); await page.reload();
 await expect(page.getByText(/Start a new run for interrupted computation/)).toBeVisible();
 await page.getByRole('button',{name:'History',exact:true}).click();
 await page.getByRole('button',{name:/Open run recover/}).click();
 await expect(page.getByRole('heading',{name:'Saved run · failed'})).toBeVisible();
 await expect(page.locator('.timeline')).toContainText('Synthetic plan');
});

test('repeated reloads keep a contiguous audit timeline without duplicate delivery',async ({context,page})=>{
 const server=await setup(context); await page.goto('/'); await page.getByRole('button',{name:'Run analysis'}).click();
 await expect(page.locator('.timeline .event')).toHaveCount(1);
 for (let i=0;i<2;i++) {await page.reload(); await expect(page.locator('.timeline .event')).toHaveCount(1);}
 server.finish();
 await expect(page.getByText('Saved in this browser',{exact:true})).toBeVisible();
 await expect(page.locator('.timeline .event')).toHaveCount(3);
 expect(server.cursors.filter(c=>c===1).length).toBeGreaterThanOrEqual(2);
});

test('a replay gap is disclosed without accepting terminal completion or losing earlier evidence',async ({context,page})=>{
 const server=await setup(context); await page.goto('/'); await page.getByRole('button',{name:'Run analysis'}).click();
 await expect(page.locator('.timeline .event')).toHaveCount(1);
 await context.route('**/api/runs/recover/event-page?*',r=>r.fulfill({json:{id:'recover',status:'completed',events:[{id:'recover:3',run_id:'recover',sequence:3,kind:'done',timestamp:'2026-11-11T12:00:00Z',message:'Untrustworthy completion',payload:{status:'completed'}}],next_sequence:3,last_sequence:3}}));
 await page.reload();
 await expect(page.getByRole('alert').filter({hasText:'gap or reordered sequence'})).toContainText('gap or reordered sequence');
 await expect(page.getByRole('button',{name:'Retry reconnection'})).toBeVisible();
 await expect(page.locator('.timeline .event')).toHaveCount(1);
 await expect(page.getByText('Saved in this browser',{exact:true})).toHaveCount(0);
});


test('worker loss preserves collected overlay bytes and names outputs that never arrived',async ({context,page})=>{
 const server=await setup(context); await page.goto('/'); await page.getByRole('button',{name:'Run analysis'}).click();
 await expect(page.locator('.timeline')).toContainText('Synthetic plan');
 server.mask(); await expect(page.getByRole('img',{name:/tumor mask overlay/})).toHaveJSProperty('naturalWidth',1);
 server.lose(); await page.reload();
 await expect(page.getByText(/Outputs never received here cannot be recovered/)).toBeVisible();
 await page.getByRole('button',{name:'History',exact:true}).click();
 await page.getByRole('button',{name:/Open run recover/}).click();
 await expect(page.getByRole('img',{name:/overlay/})).toHaveJSProperty('naturalWidth',1);
 await expect(page.getByText('12.5',{exact:false})).toBeVisible();
 await expect(page.locator('.timeline .event')).toHaveCount(2);
});

test('a slower second tab cannot overwrite the saved terminal timeline with an older prefix',async ({context,page})=>{
 const server=await setup(context); await page.goto('/'); await page.getByRole('button',{name:'Run analysis'}).click();
 await expect(page.locator('.timeline .event')).toHaveCount(1);
 const slow=await context.newPage(); let release!:()=>void;
 const held=new Promise<void>(resolve=>{release=resolve});
 await slow.route('**/api/runs/recover/event-page?*',async r=>{
   await held;
   const after=Number(new URL(r.request().url()).searchParams.get('after'));
   return r.fulfill({json:{id:'recover',status:'running',events:after===1?[{id:'recover:2',run_id:'recover',sequence:2,kind:'tool_result',timestamp:'2026-11-11T12:00:00Z',message:'Delayed synthetic result',payload:{stage:'features'}}]:[],next_sequence:2,last_sequence:2}});
 });
 await slow.goto('/'); await expect(slow.locator('.timeline .event')).toHaveCount(1);
 // Terminal state is saved by the faster subscriber before the slower tab resumes.
 server.finish(); await expect(page.getByText('Saved in this browser',{exact:true})).toBeVisible();
 release(); await expect(slow.locator(".timeline .event")).toHaveCount(2); await slow.close();
 await page.route("**/api/runs/**",r=>r.abort());
 await page.reload(); await page.getByRole('button',{name:'History',exact:true}).click();
 await page.getByRole('button',{name:/Open run recover/}).click();
 await expect(page.locator('.timeline .event')).toHaveCount(3);
});

test('a late catalog response preserves the recovered launch selection', async ({context,page}) => {
 await setup(context);
 await page.addInitScript(() => localStorage.setItem('mini-nota-active-run',JSON.stringify({nonce:'a'.repeat(32),patientIds:['LUNG1-001'],workerContext:'synthetic-worker'})));
 let release!:()=>void, releaseCreate!:()=>void;
 const held=new Promise<void>(resolve=>{release=resolve});
 const heldCreate=new Promise<void>(resolve=>{releaseCreate=resolve});
 await page.route('**/api/graphql',async route=>{
   await held;
   await route.fulfill({json:{data:{patients:[{id:'LUNG1-001',label:'Synthetic one',fixture:true},{id:'LUNG1-002',label:'Synthetic two',fixture:true}]}}});
 });
 await page.route('**/api/runs',async route=>{
   await heldCreate;
   await route.fulfill({status:201,json:{id:'recover',secret:'opaque-secret',status:'running'}});
 });
 await page.goto('/');
 await expect(page.getByText('1 patients',{exact:true})).toBeVisible();
 release();
 await expect(page.getByText('2',{exact:true})).toBeVisible();
 await expect(page.getByText('1 patients',{exact:true})).toBeVisible({timeout:1000});
 releaseCreate();
});

test('Run waits for saved-history recovery before accepting a new launch',async ({context,page})=>{
 await setup(context);
 await page.addInitScript(()=>{
   const original=IDBObjectStore.prototype.getAll;
   const state=window as typeof window & {releaseHistory?:()=>void};
   IDBObjectStore.prototype.getAll=function(...args:Parameters<typeof original>){
     const request=original.apply(this,args);
     Object.defineProperty(request,'onsuccess',{set(callback){
       request.addEventListener('success',event=>{state.releaseHistory=()=>callback.call(request,event)});
     }});
     return request;
   };
 });
 await page.goto('/');
 await expect(page.getByText('1 patients',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Run analysis'})).toBeDisabled();
 await page.evaluate(()=>(window as typeof window & {releaseHistory?:()=>void}).releaseHistory?.());
 await expect(page.getByRole('button',{name:'Run analysis'})).toBeEnabled();
});
