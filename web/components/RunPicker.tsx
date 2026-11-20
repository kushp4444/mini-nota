import type { SavedRun } from "../lib/history";
import "./run-picker.css";

export type ExampleKind = "success" | "failure";

const examples = [
  ["success", "Completed example", "Full held-out cohort"],
  ["failure", "Failure example", "Recorded exclusions"],
] as const;

export default function RunPicker({
  exampleKind,
  savedRunId,
  history,
  recovering,
  onSelectExample,
  onSelectRun,
}: {
  exampleKind: ExampleKind;
  savedRunId?: string;
  history: SavedRun[];
  recovering: boolean;
  onSelectExample: (kind: ExampleKind) => void;
  onSelectRun: (id: string) => void;
}) {
  return (
    <div className="run-history">
      <details className="result-inner-details run-picker">
        <summary id="run-history-heading">Run history</summary>
        <div className="run-picker-list">
          <table className="result-list-table" aria-labelledby="run-history-heading">
            <thead>
              <tr><th scope="col">Run</th><th scope="col">Details</th></tr>
            </thead>
            <tbody>
              {examples.map(([kind, title, description]) => (
                <tr key={kind}>
                  <th scope="row">
                    <button type="button" className="history-entry"
                      aria-pressed={!savedRunId && exampleKind === kind}
                      onClick={() => onSelectExample(kind)}>
                      {title}
                    </button>
                  </th>
                  <td>{description}</td>
                </tr>
              ))}
              {history.map(run => (
                <tr key={run.id}>
                  <th scope="row">
                    <button type="button" className="history-entry" aria-label={`Open run ${run.id}`}
                      aria-pressed={savedRunId === run.id} onClick={() => onSelectRun(run.id)}>
                      {run.id}
                    </button>
                  </th>
                  <td>
                    <time dateTime={run.createdAt}>{new Date(run.createdAt).toLocaleString()}</time>
                    {" · "}{run.patientIds.length} {run.patientIds.length === 1 ? "patient" : "patients"}
                    {" · "}{run.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {recovering && <p className="run-picker-note" role="status">Loading run history…</p>}
      </details>
    </div>
  );
}
