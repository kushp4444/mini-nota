"use client";
import { useState } from "react";
import { featureLabel } from "../lib/featureLabels";
import FeatureMeasurementLabel from "./FeatureMeasurementLabel";
import type { MaskPatientResult } from "./MaskResults";

export type FeaturePatientResult = MaskPatientResult & { feature_schema?: string[] };

function measurementNames(result: FeaturePatientResult) {
  return result.feature_schema?.length ? result.feature_schema : Object.keys(result.values);
}

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
  const schema = [...new Set(successful.flatMap(measurementNames))];
  const matchingMeasurementCounts = schema.length && successful.every(result =>
    measurementNames(result).length === schema.length
  );
  const finding = successful.length
    ? "We measured the tumors’ shape, CT intensity, and patterns in the scan."
    : failed.length
      ? "We couldn’t measure the tumors from these scans."
      : ended
        ? "No feature measurements were saved before the run ended."
        : "Once we outline the tumors, we’ll measure their shape, CT intensity, and patterns in the scan.";
  const selected = selectedIds.includes(chosen) ? chosen : selectedIds[0];
  const detail = results.find(r => r.patient_id === selected);
  function disposition(id: string) {
    const patient = results.find(r => r.patient_id === id);
    if (patient) return patient.status === "success" ? "Ready" : patient.errors.map(e => e.message).join("; ") || "Extraction failed";
    if (qcResults.some(r => r.patient_id === id && r.status !== "success")) return "Did not pass scan checks";
    if (maskResults.some(r => r.patient_id === id && r.status !== "success")) return "No tumor outline was available";
    return ended ? "No feature result saved before the run ended" : "Waiting for tumor measurements";
  }
  function numeric(value: unknown) {
    return typeof value === "number" && Number.isFinite(value) ? value.toPrecision(8) : "Unavailable";
  }
  const csv = detail?.artifacts?.find(a => a.media_type === "text/csv" && a.data_base64);
  return <section className="card results feature-results" aria-label="Radiomic features">
    <div className="card-heading"><h2>Tumor measurements from the CT scan</h2></div>
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
    <p className="result-caption">These numbers describe what the tumor looks like on the scan. CT intensity describes how light or dark each point is after the scan values are put on a common scale. Texture describes how those values vary from place to place.</p>
    <div className="feature-scroll" tabIndex={0} role="region" aria-label="Scrollable feature measurements">
      <table aria-label="Feature measurements">
        <thead><tr><th>Patient</th><th>Result</th>{schema.map(name => <th key={name}>{featureLabel(name)}</th>)}</tr></thead>
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
        {measurementNames(detail).map(name => <div key={name}><dt><FeatureMeasurementLabel name={name} /></dt><dd title={String(detail.values[name])}>{numeric(detail.values[name])}</dd></div>)}
      </dl> : null}
    </div> : <p className="muted">Start a run to see tumor measurements.</p>}
    </details> : null}
  </section>;
}
