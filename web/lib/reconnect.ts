import { captureEvent, terminal, type SavedRun, type Audit } from './history';
function interrupted(run: SavedRun, reason: string): SavedRun {
  return { ...run, status: 'failed', updatedAt: new Date().toISOString(), reason: `${reason} Saved results and artifact bytes are preserved in this browser. Outputs never received here cannot be recovered. Start a new run for interrupted computation.` };
}
export async function reconnectRun(
  initial: SavedRun,
  initialSaved: boolean,
  receive: (run: SavedRun) => Promise<boolean>,
  signal: AbortSignal,
): Promise<'waiting_approval' | void> {
  let run = initial, saved = initialSaved, failures = 0, restored = false;
  while (!terminal(run.status) && !signal.aborted) {
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(run.id)}/event-page?after=${run.lastSequence}&limit=20`, { headers: { Authorization: `Bearer ${run.secret}` }, cache: 'no-store', signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]) });
      if (signal.aborted) return;
      if (response.status === 404 && run.status === 'waiting_approval' && run.checkpoint && !restored) {
        const checkpoint = run.checkpoint as {run_id:string;last_sequence:number;patient_ids:string[]};
        // The signed gate belongs to this exact saved prefix. Never fabricate a lost timeline.
        if (checkpoint.run_id !== run.id || checkpoint.last_sequence !== run.lastSequence ||
            JSON.stringify(checkpoint.patient_ids) !== JSON.stringify(run.patientIds) ||
            run.events.length !== run.lastSequence || run.events.some((e,i) => e.run_id !== run.id || e.sequence !== i+1) ||
            run.events.at(-1)?.kind !== 'gate') {
          await receive(interrupted(run, 'Saved approval checkpoint or audit prefix is incomplete.'));
          return;
        }
        const body = JSON.stringify({checkpoint:run.checkpoint});
        if (new TextEncoder().encode(body).byteLength > 4_000_000) {
          await receive(interrupted(run, 'Saved approval exceeds the recovery request limit.'));
          return;
        }
        const recovery = await fetch('/api/runs/restore', {method:'POST',headers:{Authorization:`Bearer ${run.secret}`,'Content-Type':'application/json'},body,cache:'no-store',signal:AbortSignal.any([signal,AbortSignal.timeout(15000)])});
        if (recovery.status === 409) {
          // Another tab has recovered/advanced it. Replay its current disclosure.
          restored = true;
          continue;
        }
        if ([403,413,422].includes(recovery.status)) {
          const detail = await recovery.json().catch(() => ({}));
          await receive(interrupted(run, typeof detail.detail === 'string' ? detail.detail : 'Saved approval is incompatible or cannot be verified.'));
          return;
        }
        if (!recovery.ok) throw Error(`Approval recovery unavailable (${recovery.status}); the saved gate remains pending`);
        const result = await recovery.json();
        if (result.id !== run.id) throw Error('Recovery returned a different run identity');
        restored = true;
        continue;
      }
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
        saved = await receive(run);
      }
      if (page.next_sequence !== run.lastSequence || page.last_sequence < run.lastSequence) throw Error('Event replay cursor mismatch; completion has not been accepted');
      if (terminal(page.status) && page.last_sequence === run.lastSequence && !terminal(run.status)) throw Error('Terminal run has no final event; completion has not been accepted');
      failures = 0;
      restored = false; // A later independent worker loss can recover this still-pending gate again.
      if (page.last_sequence === run.lastSequence) {
        if (page.status === 'waiting_approval' && run.status === 'waiting_approval' && run.checkpoint) {
          if (!saved && !signal.aborted) saved = await receive(run);
          if (saved && !signal.aborted) return 'waiting_approval';
        }
        if (!terminal(run.status)) await new Promise(resolve => setTimeout(resolve, 750));
      }
    } catch (e) {
      if (signal.aborted) return;
      if (++failures >= 3) throw e;
      await new Promise(resolve => setTimeout(resolve, 750));
    }
  }
}
