"use client";
import { useState } from "react";
import type { MaskPatientResult } from "./MaskResults";

export type FeaturePatientResult = MaskPatientResult & { feature_schema?: string[] };

/** Works on live or retained results; all downloads use locally owned bytes. */
export default function FeatureResults({selectedIds, results, qcResults, maskResults,ended=false}: {
  selectedIds: string[];
  results: FeaturePatientResult[];
  qcResults: MaskPatientResult[];
  maskResults: MaskPatientResult[];
  ended?:boolean;
}) {
  const [chosen, setChosen] = useState("");
  const successful = results.filter(result => result.status === "success");
  const failed = results.filter(result => result.status !== "success");
  const schema = [...new Set(successful.flatMap(result => result.feature_schema?.length ? result.feature_schema : Object.keys(result.values)))];
  const matchingMeasurementCounts = schema.length && successful.every(result =>
    (result.feature_schema?.length || Object.keys(result.values).length) === schema.length
  );
  const finding = successful.length
    ? "Feature extraction measured tumor shape, image intensity, and texture."
    : failed.length
      ? "Feature extraction did not produce measurements."
      : ended
        ? "No feature measurements were saved before the run ended."
        : "Feature extraction measures tumor shape, image intensity, and texture after masks are created.";
  const selected = selectedIds.includes(chosen) ? chosen : selectedIds[0];
  const detail = results.find(r => r.patient_id === selected);
  function disposition(id: string) {
    const patient = results.find(r => r.patient_id === id);
    if (patient) return patient.status === "success" ? "Ready" : patient.errors.map(e => e.message).join("; ") || "Extraction failed";
    if (qcResults.some(r => r.patient_id === id && r.status !== "success")) return "Excluded by QC";
    if (maskResults.some(r => r.patient_id === id && r.status !== "success")) return "Excluded by mask failure";
    return ended ? "No feature result saved before the run ended" : "Waiting for feature extraction";
  }
  function numeric(value: unknown) {
    return typeof value === "number" && Number.isFinite(value) ? value.toPrecision(8) : "Unavailable";
  }
  const csv = detail?.artifacts?.find(a => a.media_type === "text/csv" && a.data_base64);
  return <section className="card results feature-results" aria-label="Radiomic features">
    <div className="card-heading"><h2>Radiomic features</h2></div>
    <p className="result-finding">{finding}</p>
    {!!results.length && <p className="result-caption">
      {successful.length} {successful.length === 1 ? "patient" : "patients"} with measurements
      {matchingMeasurementCounts ? ` · ${schema.length} measurements per patient` : ""}
      {failed.length ? ` · ${failed.length} extraction ${failed.length === 1 ? "failure" : "failures"}` : ""}
    </p>}
    {!!failed.length && <div className="patient-results" tabIndex={0} role="region" aria-label="Patient feature extraction failures">
      {failed.map(patient => <article className="patient-result" key={patient.patient_id}>
        <div className="patient-heading"><strong>{patient.patient_id}</strong><span className="status failed">Extraction failed</span></div>
        <p className="error-text">{disposition(patient.patient_id)}</p>
      </article>)}
    </div>}
    {(results.length || qcResults.length || maskResults.length) ? <details className="result-details">
    <summary>View details</summary>
    <div className="feature-scroll" tabIndex={0} role="region" aria-label="Scrollable feature measurements">
      <table aria-label="Feature measurements">
        <thead><tr><th>Patient</th><th>Disposition</th>{schema.map(name => <th key={name}>{name}</th>)}</tr></thead>
        <tbody>{selectedIds.map(id => {
          const patient = results.find(r => r.patient_id === id);
          return <tr key={id} aria-selected={selected === id}>
            <td><button className="patient-link" aria-label={`Inspect ${id}`} onClick={() => setChosen(id)}>{id}</button></td>
            <td>{disposition(id)}</td>
            {schema.map(name => <td key={name}>{patient?.status === "success" ? numeric(patient.values[name]) : "—"}</td>)}
          </tr>;
        })}</tbody>
      </table>
    </div>
    {selected ? <div className="feature-detail">
      <div className="patient-heading"><h3>{selected} feature details</h3>
        {csv ? <a download={`${selected}-features.csv`} href={`data:text/csv;base64,${csv.data_base64}`} aria-label={`Download ${selected} features CSV`}>Download CSV ↓</a> : null}
      </div>
      <p className={detail?.status === "failed" ? "error-text" : "muted"}>{disposition(selected)}</p>
      {detail?.status === "success" ? <dl className="feature-values">
        {(detail.feature_schema?.length ? detail.feature_schema : Object.keys(detail.values)).map(name => <div key={name}><dt>{name}</dt><dd title={String(detail.values[name])}>{numeric(detail.values[name])}</dd></div>)}
      </dl> : null}
    </div> : <p className="muted">Start a run to inspect radiomic measurements.</p>}
    </details> : null}
  </section>;
}
