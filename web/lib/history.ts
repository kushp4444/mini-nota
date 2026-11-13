/** Versioned local History records, including downloaded artifact bytes. */
export type Audit = {
  id: string;
  run_id: string;
  sequence: number;
  timestamp: string;
  kind: string;
  message: string;
  payload: Record<string, any>;
};
export type SavedArtifact = {
  version: 1;
  id: string;
  stage: string;
  patientId?: string;
  role: string;
  mediaType: string;
  blob?: Blob;
  error?: string;
  metadata: Record<string, unknown>;
};
export type SavedRun = {
  version: 1;
  id: string;
  secret: string;
  launchNonce?: string;
  patientIds: string[];
  createdAt: string;
  updatedAt: string;
  status: string;
  reason?: string;
  events: Audit[];
  artifacts: SavedArtifact[];
  lastSequence: number;
  checkpoint?: unknown;
};
export const terminal = (status: string) =>
  ["completed", "failed", "canceled"].includes(status);
const DB = "mini-nota-history";
function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!globalThis.indexedDB)
      return reject(new Error("Browser storage is unavailable"));
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () =>
      request.result.createObjectStore("runs", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () =>
      reject(new Error("Browser storage upgrade is blocked by another tab"));
  });
}
export function storageMessage(error: unknown) {
  const name = error instanceof DOMException ? error.name : "";
  return name === "QuotaExceededError"
    ? "Browser storage is full. This run is not safely saved; results may be lost when you leave."
    : "Browser history is unavailable or could not be saved. Results may be lost when you leave. " +
        (error instanceof Error ? error.message : "");
}
/** Keep already downloaded bytes when a different replay or tab writes a snapshot. */
export function retainArtifactBytes(run: SavedRun, other?: SavedRun): SavedRun {
  if (other?.id !== run.id) return run;
  const byId = new Map(other.artifacts.filter(artifact => artifact.blob).map(artifact => [artifact.id, artifact]));
  const artifacts = run.artifacts.map(artifact => artifact.blob ? artifact : byId.get(artifact.id) ?? artifact);
  return {...run, artifacts};
}

export async function saveRun(run: SavedRun): Promise<SavedRun> {
  const db = await open();
  try {
    return await new Promise<SavedRun>((resolve, reject) => {
      const tx = db.transaction("runs", "readwrite");
      const records = tx.objectStore("runs");
      const existing = records.get(run.id);
      let snapshot = run;
      existing.onsuccess = () => {
        const saved = existing.result as SavedRun | undefined;
        // Another tab may already have saved a longer prefix or final outcome.
        const newer = saved && (saved.lastSequence > run.lastSequence ||
          (saved.lastSequence === run.lastSequence && terminal(saved.status) && !terminal(run.status)));
        snapshot = newer ? retainArtifactBytes(saved, run) : retainArtifactBytes(run, saved);
        try { records.put(snapshot); }
        catch (error) { tx.abort(); reject(error); }
      };
      tx.oncomplete = () => resolve(snapshot);
      tx.onabort = () => reject(tx.error || new Error("Storage write aborted"));
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}
export async function readRuns(): Promise<SavedRun[]> {
  const db = await open();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("runs", "readonly");
      const request = tx.objectStore("runs").getAll();
      request.onsuccess = () => {
        const runs = request.result as SavedRun[];
        if (
          runs.some(
            (run) =>
              run.version !== 1 ||
              !Array.isArray(run.events) ||
              !Array.isArray(run.artifacts) ||
              !Array.isArray(run.patientIds),
          )
        ) {
          reject(
            new Error(
              "Saved history has an unsupported or damaged format. It cannot be safely displayed.",
            ),
          );
          return;
        }
        resolve(runs.sort((a, b) => b.createdAt.localeCompare(a.createdAt)));
      };
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}
export function createSavedRun(
  run: { id: string; secret: string; status: string },
  patientIds: string[],
): SavedRun {
  const now = new Date().toISOString();
  return {
    version: 1,
    ...run,
    patientIds: [...patientIds],
    createdAt: now,
    updatedAt: now,
    events: [],
    artifacts: [],
    lastSequence: 0,
  };
}
async function downloadArtifact(url: string, secret: string): Promise<Blob> {
  const target = new URL(url, window.location.origin);
  if (target.origin !== window.location.origin)
    throw Error("Artifact URL must use the application proxy");
  const response = await fetch(target, {
    headers: { Authorization: `Bearer ${secret}` },
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw Error(`Artifact unavailable (${response.status})`);
  return response.blob();
}

function artifactSources(event: Audit) {
  return [...(event.payload.artifacts || []), ...(event.payload.patient?.artifacts || [])];
}

/** Derive a stable authenticated endpoint from the saved event, including older records. */
function artifactEndpoint(run: SavedRun, artifact: SavedArtifact) {
  if (!run.secret || artifact.blob) return;
  const delimiter = artifact.id.lastIndexOf(":");
  const index = Number(artifact.id.slice(delimiter + 1));
  const event = run.events.find(item => item.id === artifact.id.slice(0, delimiter));
  if (event?.run_id !== run.id || !Number.isSafeInteger(index) || !artifactSources(event)[index]) return;
  return `/api/runs/${encodeURIComponent(run.id)}/artifacts/${event.sequence}/${index}`;
}

export function canRecoverArtifact(run: SavedRun, artifact: SavedArtifact) {
  return Boolean(artifactEndpoint(run, artifact));
}

export async function recoverArtifact(run: SavedRun, artifact: SavedArtifact): Promise<SavedArtifact> {
  const endpoint = artifactEndpoint(run, artifact);
  if (!endpoint) return artifact;
  const blob = await downloadArtifact(endpoint, run.secret);
  return {...artifact, blob, error: undefined};
}

/** Capture bytes now; saved records never depend on an engine path or temporary URL. */
export async function captureEvent(
  run: SavedRun,
  event: Audit,
): Promise<SavedRun> {
  if (terminal(run.status) || run.events.some((e) => e.id === event.id)) return run;
  const artifacts: SavedArtifact[] = [];
  const stage = event.payload.stage || "unknown";
  const patient = event.payload.patient;
  const sources = artifactSources(event);
  for (const [index, source] of sources.entries()) {
    const { data_base64, url, path, ...metadata } = source;
    const artifact: SavedArtifact = {
      version: 1,
      id: `${event.id}:${index}`,
      stage,
      patientId: patient?.patient_id,
      role: source.role || "artifact",
      mediaType: source.media_type || "application/octet-stream",
      metadata,
    };
    try {
      if (data_base64) {
        const bytes = Uint8Array.from(atob(data_base64), (c) =>
          c.charCodeAt(0),
        );
        artifact.blob = new Blob([bytes], { type: artifact.mediaType });
      } else if (url) {
        artifact.blob = await downloadArtifact(url, run.secret);
      } else throw Error("Artifact bytes were not supplied by the engine");
    } catch (e) {
      artifact.error =
        e instanceof Error ? e.message : "Artifact could not be saved";
    }
    artifacts.push(artifact);
  }
  // Remove transient transport fields while retaining every structured result and metadata.
  const cleaned: Audit = structuredClone(event);
  const cleanArtifacts = (items: Record<string, unknown>[] | undefined) =>
    items?.map((item) => {
      const { data_base64, url, path, ...metadata } = item;
      return metadata;
    });
  if (cleaned.payload.artifacts)
    cleaned.payload.artifacts = cleanArtifacts(cleaned.payload.artifacts);
  if (cleaned.payload.patient?.artifacts)
    cleaned.payload.patient.artifacts = cleanArtifacts(
      cleaned.payload.patient.artifacts,
    );
  const events = [...run.events, cleaned].sort(
    (a, b) => a.sequence - b.sequence,
  );
  const isDone = event.kind === "done";
  return {
    ...run,
    events,
    artifacts: [...run.artifacts, ...artifacts],
    updatedAt: new Date().toISOString(),
    lastSequence: Math.max(run.lastSequence, event.sequence),
    status: isDone ? event.payload.status || "completed" : event.payload.status || run.status,
    reason: isDone
      ? event.payload.reason ||
        (event.payload.status === "failed"
          ? [
              event.message,
              [...events].reverse().find((e) => e.kind === "error")?.message,
            ]
              .filter(Boolean)
              .join(" ")
          : event.message)
      : run.reason,
    checkpoint: event.payload.checkpoint ?? run.checkpoint,
  };
}
