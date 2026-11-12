/** Same-browser coordination only: per-run capabilities, no visitor identity. */
const KEY = 'mini-nota-active-run';
const SIGNAL = 'mini-nota-run-change';
export type PendingLaunch = { nonce: string; patientIds: string[]; workerContext?: string };
export function pendingLaunch(): PendingLaunch | undefined {
  const value = localStorage.getItem(KEY);
  if (!value?.startsWith('{')) return;
  const launch = JSON.parse(value);
  if (typeof launch.nonce !== 'string' || !Array.isArray(launch.patientIds)) throw Error('Saved launch recovery data is damaged.');
  return launch;
}
export function browserRun(): string | null {
  return pendingLaunch()?.nonce || localStorage.getItem(KEY);
}
function publish() { window.dispatchEvent(new Event(SIGNAL)); }
export function watchBrowserRun(update: () => void) {
  window.addEventListener('storage', update);
  window.addEventListener(SIGNAL, update);
  update();
  return () => { window.removeEventListener('storage', update); window.removeEventListener(SIGNAL, update); };
}
export async function reserveBrowserRun(patientIds: string[] = []): Promise<string> {
  if (!navigator.locks) throw Error('This browser cannot safely coordinate runs across tabs. Use a browser supporting Web Locks.');
  return navigator.locks.request('mini-nota-run-control', () => {
    if (browserRun()) throw Error('A run is already active or awaiting approval in this browser. Finish or cancel it before starting another.');
    const nonce = crypto.randomUUID();
    localStorage.setItem(KEY, JSON.stringify({nonce, patientIds}));
    publish(); return nonce;
  });
}
export function rememberLaunchContext(nonce: string, workerContext: string) {
  const launch = pendingLaunch();
  if (launch?.nonce !== nonce) throw Error('Launch recovery reservation changed in another tab');
  localStorage.setItem(KEY, JSON.stringify({...launch, workerContext}));
}
export async function reclaimBrowserRun(id: string) {
  if (!navigator.locks) return;
  await navigator.locks.request('mini-nota-run-control', () => {
    if (!browserRun()) {localStorage.setItem(KEY, id); publish();}
  });
}
export function attachBrowserRun(token: string, id: string) {
  if (browserRun() === token) { localStorage.setItem(KEY, id); publish(); }
}
export function releaseBrowserRun(id: string) {
  if (browserRun() === id) { localStorage.removeItem(KEY); publish(); }
}
