/** Same-browser coordination only: opaque run references, no visitor identity. */
const KEY = 'mini-nota-active-run';
const SIGNAL = 'mini-nota-run-change';
export function browserRun(): string | null {
  return localStorage.getItem(KEY);
}
function publish() { window.dispatchEvent(new Event(SIGNAL)); }
export function watchBrowserRun(update: () => void) {
  window.addEventListener('storage', update);
  window.addEventListener(SIGNAL, update);
  update();
  return () => {
    window.removeEventListener('storage', update);
    window.removeEventListener(SIGNAL, update);
  };
}
export async function reserveBrowserRun(): Promise<string> {
  if (!navigator.locks) throw Error('This browser cannot safely coordinate runs across tabs. Use a browser supporting Web Locks.');
  return navigator.locks.request('mini-nota-run-control', () => {
    if (browserRun()) throw Error('A run is already active or awaiting approval in this browser. Finish or cancel it before starting another.');
    const token = `starting:${crypto.randomUUID()}`;
    localStorage.setItem(KEY, token);
    publish();
    return token;
  });
}
export function attachBrowserRun(token: string, id: string) {
  if (browserRun() === token) { localStorage.setItem(KEY, id); publish(); }
}
export function releaseBrowserRun(id: string) {
  if (browserRun() === id) { localStorage.removeItem(KEY); publish(); }
}
