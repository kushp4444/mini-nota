import { PendingLaunch, rememberLaunchContext } from './browser-run';
export class StoppedLaunch extends Error {}
export async function recoverLaunch(launch: PendingLaunch): Promise<{id: string; secret: string; status: string}> {
  let worker = launch.workerContext;
  if (!worker) {
    const context = await fetch('/api/runs/launch-context', {cache:'no-store',signal:AbortSignal.timeout(15000)});
    if (!context.ok) throw Error('Cannot contact the runner. Retry launch recovery.');
    worker = (await context.json()).worker_context;
    if (!worker) throw Error('Runner did not provide launch recovery context');
    // This write happens before creation can reach the server.
    rememberLaunchContext(launch.nonce, worker!);
  }
  const created = await fetch('/api/runs', {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({patient_ids:launch.patientIds,launch_nonce:launch.nonce,worker_context:worker}),signal:AbortSignal.timeout(35000)});
  const result = await created.json();
  if (!created.ok) {
    if (result.detail?.code === 'launch_interrupted' || created.status === 422)
      throw new StoppedLaunch(typeof result.detail === 'string' ? result.detail : result.detail?.message || 'Selection rejected; start a new run.');
    throw Error(typeof result.detail === 'string' ? result.detail : 'Launch recovery unavailable. Retry before starting another run.');
  }
  return result;
}
