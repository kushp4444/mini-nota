import { PendingLaunch, pendingLaunch, rememberLaunchContext } from './browser-run';
export class StoppedLaunch extends Error {}
export class LaunchNotStarted extends Error {}
export async function recoverLaunch(launch: PendingLaunch): Promise<{id: string; secret: string; status: string}> {
  const worker = launch.workerContext ?? await navigator.locks.request('mini-nota-launch-context', async () => {
    // Two tabs recovering the first launch must not mint competing quota cookies.
    const saved = pendingLaunch();
    if (saved?.nonce === launch.nonce && saved.workerContext) return saved.workerContext;
    const context = await fetch('/api/runs/launch-context', {cache:'no-store',signal:AbortSignal.timeout(15000)});
    if (!context.ok) throw Error('Cannot contact the runner. Retry launch recovery.');
    const { worker_context: worker } = await context.json();
    if (typeof worker !== 'string' || !worker) throw Error('Runner did not provide launch recovery context');
    // This write happens before creation can reach the server.
    rememberLaunchContext(launch.nonce, worker);
    return worker;
  });
  const created = await fetch('/api/runs', {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({patient_ids:launch.patientIds,launch_nonce:launch.nonce,worker_context:worker}),signal:AbortSignal.timeout(35000)});
  const result = await created.json();
  if (!created.ok) {
    if (created.status === 429 && result.detail?.code === 'launch_quota') {
      const retry = new Date(result.detail.retry_at).toLocaleString(undefined, {
        dateStyle: 'medium', timeStyle: 'short',
      });
      throw new LaunchNotStarted(`You've reached the live run limit. Try again after ${retry}.`);
    }
    if (created.status === 428)
      throw new LaunchNotStarted('Allow cookies for this site before starting a new live run.');
    if (result.detail?.code === 'launch_interrupted' || created.status === 422)
      throw new StoppedLaunch(typeof result.detail === 'string' ? result.detail : result.detail?.message || 'Selection rejected; start a new run.');
    throw Error(typeof result.detail === 'string' ? result.detail : 'Launch recovery unavailable. Retry before starting another run.');
  }
  return result;
}
