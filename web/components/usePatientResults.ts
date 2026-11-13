"use client";

import { useEffect, useState } from "react";
import type { SavedRun } from "../lib/history";
import type { FeaturePatientResult } from "./FeatureResults";

const stages = ["qc", "masks", "features"] as const;
type Results = Record<(typeof stages)[number], FeaturePatientResult[]>;
const empty: Results = {qc: [], masks: [], features: []};

/** Hydrate each patient artifact from the same event and index that captured it. */
export default function usePatientResults(run?: SavedRun): Results {
  const [retained, setRetained] = useState<{runId: string; results: Results}>();
  useEffect(() => {
    if (!run) return;
    let current = true;
    const byId = new Map(run.artifacts.map(artifact => [artifact.id, artifact]));
    const results: Results = {qc: [], masks: [], features: []};
    void (async () => {
      for (const event of run.events) {
        const stage = event.payload.stage;
        if (event.kind !== "tool_result" || !stages.includes(stage) || !event.payload.patient) continue;
        const patient: FeaturePatientResult = structuredClone(event.payload.patient);
        const offset = event.payload.artifacts?.length ?? 0;
        for (const [index, artifact] of (patient.artifacts ?? []).entries()) {
          const saved = byId.get(`${event.id}:${offset + index}`);
          if (saved && saved.stage === stage && saved.blob) {
            artifact.data_base64 = await new Promise<string | undefined>(resolve => {
              const reader = new FileReader();
              reader.onload = () => resolve(String(reader.result).split(",")[1]);
              reader.onerror = reader.onabort = () => resolve(undefined);
              reader.readAsDataURL(saved.blob!);
            });
          }
        }
        results[stage as keyof Results].push(patient);
      }
      if (current) setRetained({runId: run.id, results});
    })();
    return () => { current = false; };
  }, [run]);
  return run && retained?.runId === run.id ? retained.results : empty;
}
