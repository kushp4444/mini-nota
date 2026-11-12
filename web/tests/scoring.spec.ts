import { writeFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";

// Release check against the actual frozen 82-patient catalog and real Python tools.
test("real held-out patient receives frozen model score and retains it in History", async ({ page, request }) => {
  test.setTimeout(120000);
  const catalog = await request.post('/api/graphql', { data: { query: '{ patients { id fixture } modelMetadata { model_version reference_count development_count held_out_count } }' } });
  const { data, errors } = await catalog.json();
  expect(errors).toBeUndefined();
  expect(data.patients).toHaveLength(82);
  expect(data.modelMetadata.development_count).toBe(332);
  expect(data.modelMetadata.reference_count).toBe(332);
  const id = data.patients[0].id;
  await page.goto('/');
  await expect(page.getByText('82 available patients')).toBeVisible();
  await page.getByLabel('Select all patients').uncheck();
  await page.getByLabel(`Select ${id}`, {exact:true}).check();
  await page.getByRole('button',{name:'Run analysis'}).click();
  const scores = page.getByLabel('Frozen model risk scores', {exact:true});
  await expect(scores.getByText('1 / 1 scored',{exact:true})).toBeVisible({timeout:90000});
  await expect(scores.getByText(data.modelMetadata.model_version,{exact:true})).toBeVisible();
  await expect(page.getByText('Saved in this browser',{exact:true})).toBeVisible();
  await expect(page.getByLabel('Tumor masks',{exact:true}).getByRole('img')).toBeVisible();
  const saved = await page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve,reject) => { const req=indexedDB.open('mini-nota-history');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error); });
    const rows = await new Promise<any[]>((resolve,reject) => {const req=db.transaction('runs').objectStore('runs').getAll();req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});db.close();
    return rows[0];
  });
  const query = 'query($id: ID!){ runResults(id:$id){ id status patient_ids model_version scores { patient_id risk_score model_version } } }';
  const forbidden = await request.post('/api/graphql',{data:{query,variables:{id:saved.id}}});
  expect((await forbidden.json()).errors).toBeDefined();
  const result = await request.post('/api/graphql',{headers:{Authorization:`Bearer ${saved.secret}`},data:{query,variables:{id:saved.id}}});
  const scored = (await result.json()).data.runResults;
  await writeFile('/private/tmp/mini-nota-implementation/ticket7-live-receipt.json',JSON.stringify({patient_id:id,model_version:scored.model_version,risk_score:scored.scores[0].risk_score,events:saved.events.map((e:any)=>({timestamp:e.timestamp,kind:e.kind,stage:e.payload.stage})),artifact_count:saved.artifacts.length},null,2));
  await page.screenshot({path:'/private/tmp/mini-nota-implementation/ticket7-live-scoring.png',fullPage:true});
  expect(scored.status).toBe('completed');
  expect(scored.scores[0].patient_id).toBe(id);
  expect(scored.model_version).toBe(data.modelMetadata.model_version);
  expect(scored.scores[0].risk_score).toBe(saved.events.find((e:any)=>e.payload.stage==='score'&&e.kind==='tool_result').payload.patient.values.risk_score);
  await page.getByRole('button',{name:'History',exact:true}).click();
  await page.getByRole('button',{name:`Open run ${saved.id}`,exact:true}).click();
  await expect(page.getByRole('heading',{name:'Model risk scores',exact:true})).toBeVisible();
  await page.reload();
  await page.getByRole('button',{name:'History',exact:true}).click();
  await page.getByRole('button',{name:`Open run ${saved.id}`,exact:true}).click();
  await expect(page.getByRole('heading',{name:'Model risk scores',exact:true})).toBeVisible();
});
