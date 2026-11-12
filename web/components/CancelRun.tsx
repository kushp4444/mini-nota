'use client';
import { useState } from 'react';
export default function CancelRun({ onConfirm }: { onConfirm: () => Promise<void> }) {
  const [open, setOpen] = useState(false), [pending, setPending] = useState(false), [error, setError] = useState('');
  async function confirm() {
    setPending(true); setError('');
    try { await onConfirm(); setOpen(false); }
    catch (e) { setError(e instanceof Error ? e.message : 'Cancellation could not be confirmed. Please retry.'); }
    finally { setPending(false); }
  }
  return <>
    <button onClick={() => setOpen(true)}>Cancel run</button>
    {open && <div className="cancel-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="cancel-title" className="card cancel-dialog">
      <h2 id="cancel-title">Cancel this run?</h2>
      <p>This stops current processing. Available results will remain in this browser’s History.</p>
      {error && <p role="alert">{error}</p>}
      <button autoFocus disabled={pending} onClick={() => setOpen(false)}>Keep running</button>
      <button className="primary" disabled={pending} onClick={confirm}>{pending ? 'Stopping work…' : 'Confirm cancellation'}</button>
    </section></div>}
  </>;
}
