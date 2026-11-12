import { captureEvent, createSavedRun, type Audit, type SavedRun } from './history';

export type Example = SavedRun & {
  example: {description:string;faults:string[];provenance:Record<string,string>};
};
/** Static, capability-free executions use the same event and artifact capture as History. */
export async function loadExample(kind:'success'|'failure'): Promise<Example> {
  const response = await fetch(`/examples/curated-${kind}.json`);
  if (!response.ok) throw Error('Curated example unavailable. Please retry.');
  const asset = await response.json();
  let run = {...createSavedRun({id:asset.id,secret:'',status:'running'},asset.patientIds),createdAt:asset.createdAt};
  for (const event of asset.events as Audit[]) run = await captureEvent(run,event);
  return {...run,example:{description:asset.description,faults:asset.faults,provenance:asset.provenance}};
}
