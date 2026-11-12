import {test,expect} from '@playwright/test';
// Synthetic API fixture verifies browser gate persistence; real tools are covered by API tests.
for (const scenario of ['restore','restore-again','restore-conflict','invalid-checkpoint','lost-local-data'] as const) test(`saved approval recovery: ${scenario}`,async({context,page})=>{
 let approved=false, approvals=0, lost=false, restores=0, recoveredPages=0;
 const report={scoring_eligible_count:1,evaluation_eligible_count:0,dispositions:[{patient_id:'FIXTURE-FLAGGED',scoring_eligible:false,evaluation_eligible:false,reasons:[{message:'Privacy scan check failed'}]},{patient_id:'FIXTURE-MISSING',scoring_eligible:true,evaluation_eligible:false,reasons:[{message:'No recorded outcome; risk scoring remains available'}]}]};
 const checkpoint={version:1,run_id:'gate-fixture',patient_ids:['FIXTURE-FLAGGED','FIXTURE-MISSING'],model_version:'fixture-model',feature_version:'fixture-features',feature_rows:[{patient_id:'FIXTURE-MISSING',values:{measurement:1},feature_schema:['measurement'],feature_version:'fixture-features'}],eligibility:report,disclosure_id:'cohort-content-hash',last_sequence:1};
 const events=[{kind:'gate',message:'Synthetic exclusions require approval',payload:{status:'waiting_approval',report,checkpoint}},{kind:'decision',message:'Anonymous run approval recorded',payload:{action:'approve',status:'running'}},{kind:'done',message:'Synthetic scoring completed',payload:{status:'completed'}}].map((e,i)=>({...e,id:`gate-fixture:${i+1}`,run_id:'gate-fixture',sequence:i+1,timestamp:'2026-11-12T12:00:00Z'}));
 await context.route('**/api/graphql',r=>r.fulfill({json:{data:{patients:checkpoint.patient_ids.map(id=>({id,label:'Synthetic fixture',fixture:true}))}}}));
 await context.route('**/api/runs/launch-context',r=>r.fulfill({json:{worker_context:'fixture-worker'}}));
 await context.route('**/api/runs',r=>r.fulfill({status:201,json:{id:'gate-fixture',secret:'fixture-secret',status:'running'}}));
 await context.route('**/api/runs/gate-fixture/event-page?*',r=>{if(lost)return r.fulfill({status:404,json:{detail:'Temporary run unavailable'}});if(restores)recoveredPages++;const after=Number(new URL(r.request().url()).searchParams.get('after'));const available=approved?events:events.slice(0,1);return r.fulfill({json:{id:'gate-fixture',status:approved?'completed':'waiting_approval',events:available.filter(e=>e.sequence>after),next_sequence:available.length,last_sequence:available.length}})});
 await context.route('**/api/runs/gate-fixture/approve',r=>{expect(r.request().headers().authorization).toBe('Bearer fixture-secret');expect(r.request().postDataJSON()).toEqual({disclosure_id:'cohort-content-hash',model_version:'fixture-model'});approvals++;approved=true;return r.fulfill({json:{id:'gate-fixture',status:'running'}})});
 await context.route('**/api/runs/restore',r=>{expect(r.request().headers().authorization).toBe('Bearer fixture-secret');expect(r.request().postDataJSON()).toEqual({checkpoint});restores++;if(scenario==='invalid-checkpoint')return r.fulfill({status:422,json:{detail:'Saved approval is incompatible; keep History and start a new run.'}});lost=false;if(scenario==='restore-conflict')return r.fulfill({status:409,json:{detail:'A newer disclosure exists; reconnect and review the current gate'}});return r.fulfill({json:{id:'gate-fixture',status:'waiting_approval'}})});
 await page.goto('/');await page.getByRole('button',{name:'Run analysis'}).click();
 const gate=page.getByLabel('Patient exclusion approval');
 await expect(gate).toContainText('1 scoring-eligible patients · 0 evaluation-eligible patients');
 await expect(page.getByText('Approval gate saved in this browser',{exact:true})).toBeVisible();
 await expect(gate).toContainText('FIXTURE-FLAGGED');await expect(gate).toContainText('No recorded outcome');
 if(scenario==='lost-local-data') {
   await page.close();const returned=await context.newPage();
   // Delete origin storage with no app subscriber alive to write another prefix.
   await returned.goto('/missing-local-data-test');
   await returned.evaluate(async()=>{localStorage.clear();await new Promise<void>((resolve,reject)=>{const r=indexedDB.deleteDatabase('mini-nota-history');r.onsuccess=()=>resolve();r.onerror=()=>reject(r.error);});});
   await returned.goto('/');await expect(returned.getByRole('button',{name:'Run analysis'})).toBeEnabled();
   await expect(returned.getByLabel('Patient exclusion approval')).toHaveCount(0);
   expect(restores).toBe(0);expect(approvals).toBe(0);return;
 }
 lost=true;await page.clock.setFixedTime(new Date('2046-11-12T12:00:00Z'));
 await page.reload();await expect.poll(()=>restores).toBe(1);
 if(scenario==='invalid-checkpoint') {
   await expect(page.getByRole('alert').filter({hasText:'Saved approval is incompatible'})).toBeVisible();
   await page.getByRole('button',{name:'Patients',exact:true}).click();
   await expect(page.getByRole('button',{name:'Run analysis'})).toBeEnabled();
   await page.getByRole('button',{name:'History',exact:true}).click();await page.getByRole('button',{name:'Open run gate-fixture',exact:true}).click();
   await expect(page.locator('.timeline .event')).toHaveCount(1);expect(approvals).toBe(0);return;
 }
 if(scenario==='restore-again') {await expect.poll(()=>recoveredPages).toBeGreaterThan(0);await page.waitForTimeout(100);lost=true;await expect.poll(()=>restores).toBe(2);}
 await expect(gate).toContainText('Waiting has no deadline');expect(approved).toBe(false);
 await gate.getByRole('button',{name:'Approve disclosed cohort and score'}).click();
 await expect(page.getByText('Saved in this browser',{exact:true})).toBeVisible();
 await expect(gate).toHaveCount(0);expect(approvals).toBe(1);
 await page.reload();await page.getByRole('button',{name:'History',exact:true}).click();await page.getByRole('button',{name:'Open run gate-fixture',exact:true}).click();await expect(page.locator('.timeline .event')).toHaveCount(3);
});
