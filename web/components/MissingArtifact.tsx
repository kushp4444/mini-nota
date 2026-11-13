"use client";

import { useState } from "react";
import { canRecoverArtifact, type SavedArtifact, type SavedRun } from "../lib/history";

export type ArtifactRecovery = (run: SavedRun, artifact: SavedArtifact) => Promise<void>;

export default function MissingArtifact({run, artifact, onRecover}: {
  run: SavedRun;
  artifact: SavedArtifact;
  onRecover?: ArtifactRecovery;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <div>
    <p role="alert" className="error-text">
      Missing artifact: {artifact.role}. {artifact.patientId && `${artifact.patientId}. `}
      {error || artifact.error || "Saved bytes are unavailable."}
    </p>
    {onRecover && canRecoverArtifact(run, artifact) && (
      <button disabled={busy} onClick={async () => {
        setBusy(true);
        setError("");
        try { await onRecover(run, artifact); }
        catch (failure) { setError(failure instanceof Error ? failure.message : "Artifact recovery failed"); }
        finally { setBusy(false); }
      }}>{busy ? "Downloading…" : `Retry ${artifact.role} download`}</button>
    )}
  </div>;
}
