import { captureEvent, terminal, type SavedRun, type Audit } from './history';
function interrupted(run: SavedRun, reason: string): SavedRun {
  return { ...run, status: 'failed', updatedAt: new Date().toISOString(), reason: `${reason} Saved results and artifact bytes are preserved in this browser. Outputs never received here cannot be recovered. Start a new run for interrupted computation.` };
}
export async function reconnectRun(initial: SavedRun, receive: (run: SavedRun) => Promise<void>, signal: AbortSignal): Promise<void> {
  let run = initial, failures = 0;
  while (!terminal(run.status) && !signal.aborted) {
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(run.id)}/event-page?after=${run.lastSequence}&limit=20`, { headers: { Authorization: `Bearer ${run.secret}` }, cache: 'no-store', signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]) });
      if (signal.aborted) return;
      if ([403,404].includes(response.status)) {
        await receive(interrupted(run, response.status === 404 ? 'Interrupted: temporary worker state is gone.' : 'Interrupted: the saved run credentials no longer grant access.'));
        return;
      }
      if (!response.ok) throw Error(`Run connection unavailable (${response.status})`);
      const page = await response.json();
      if (page.id !== run.id || !Array.isArray(page.events) || !Number.isInteger(page.last_sequence)) throw Error('Invalid event replay response');
      const expectedEnd = run.lastSequence + page.events.length;
      if (page.next_sequence !== expectedEnd || page.last_sequence < expectedEnd ||
          page.events.some((event: Audit, i: number) => event.run_id !== run.id || event.sequence !== run.lastSequence + i + 1 || (event.kind === 'done' && (event.sequence !== page.last_sequence || event.payload.status !== page.status || !terminal(page.status)))))
        throw Error('Event replay contains a gap or reordered sequence; completion has not been accepted');
      for (const event of page.events as Audit[]) {
        if (event.run_id !== run.id || event.sequence !== run.lastSequence + 1) throw Error('Event replay contains a gap or reordered sequence; completion has not been accepted');
        run = await captureEvent(run, event);
        if (signal.aborted) return;
        await receive(run);
      }
      if (page.next_sequence !== run.lastSequence || page.last_sequence < run.lastSequence) throw Error('Event replay cursor mismatch; completion has not been accepted');
      if (terminal(page.status) && page.last_sequence === run.lastSequence && !terminal(run.status)) throw Error('Terminal run has no final event; completion has not been accepted');
      failures = 0;
      if (!terminal(run.status) && page.last_sequence === run.lastSequence) await new Promise(resolve => setTimeout(resolve, 750));
    } catch (e) {
      if (signal.aborted) return;
      if (++failures >= 3) throw e;
      await new Promise(resolve => setTimeout(resolve, 750));
    }
  }
}
