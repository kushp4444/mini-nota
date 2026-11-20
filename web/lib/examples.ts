import success from '../public/examples/curated-success.json';
import failure from '../public/examples/curated-failure.json';
import type { Audit, SavedArtifact, SavedRun } from './history';

type ExampleKind = 'success' | 'failure';
export type Example = SavedRun & {
  example: {
    faults: string[];
    files: Record<string, string>;
  };
};

function prepareExample(asset: typeof success | typeof failure): Example {
  const events: Audit[] = asset.events;
  const artifacts: SavedArtifact[] = [];
  const files: Record<string, string> = {};
  for (const event of events) {
    const { stage, artifacts: runArtifacts = [], patient } = event.payload;
    const sources = [...runArtifacts, ...(patient?.artifacts ?? [])];
    for (const [index, source] of sources.entries()) {
      const { file, ...metadata } = source;
      const id = `${event.id}:${index}`;
      if (file) files[id] = `/examples/files/${file}`;
      artifacts.push({
        version: 1,
        id,
        stage,
        patientId: patient?.patient_id,
        role: source.role,
        mediaType: source.media_type,
        metadata,
      });
    }
  }
  const lastEvent = events[events.length - 1];
  return {
    version: 1,
    id: asset.id,
    secret: '',
    status: asset.status,
    patientIds: asset.patientIds,
    createdAt: asset.createdAt,
    updatedAt: lastEvent.timestamp,
    lastSequence: lastEvent.sequence,
    events,
    artifacts,
    example: { faults: asset.faults, files },
  };
}

export const curatedExamples: Record<ExampleKind, Example> = {
  success: prepareExample(success),
  failure: prepareExample(failure),
};
