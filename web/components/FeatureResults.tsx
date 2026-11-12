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
  const schema = results.find(r => r.status === "success")?.feature_schema || [];
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
    <div className="card-heading">
      <div><h2>Radiomic features</h2><p>Configured PyRadiomics · shape, intensity and texture · {schema.length} measurements per successful patient</p></div>
      <span>{results.filter(r => r.status === "success").length} feature rows ready</span>
    </div>
    {!results.length && !qcResults.length && !maskResults.length ? <p className="stage-empty">Radiomic measurements appear after tumor masks.</p> : <>
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
        {(detail.feature_schema || []).map(name => <div key={name}><dt>{name}</dt><dd title={String(detail.values[name])}>{numeric(detail.values[name])}</dd></div>)}
      </dl> : null}
    </div> : <p className="muted">Start a run to inspect radiomic measurements.</p>}
    </>}
  </section>;
}
