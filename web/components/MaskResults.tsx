"use client";

import { useId, useState, type ReactNode } from "react";

export type MaskPatientResult = {
  patient_id: string;
  status: string;
  values: Record<string, unknown>;
  errors: { code?: string; message: string }[];
  artifacts?: { role?: string; media_type: string; data_base64?: string; imageUrl?: string }[];
};

/** Render retained stage values and bytes; no expiring server URLs. */
export default function MaskResults({ selectedIds, results, qcResults, ended=false, compact=false, children }: {
  selectedIds: string[];
  results: MaskPatientResult[];
  qcResults: MaskPatientResult[];
  ended?:boolean;
  compact?: boolean;
  children?: ReactNode;
}) {
  const ready = results.filter(result => result.status === "success").length;
  const failures = results.length - ready;
  const finding = ready
    ? ready === 1 ? "A tumor mask was created from the CT scan." : "Tumor masks were created from the CT scans."
    : results.length
      ? "Mask construction did not produce a tumor mask."
      : ended
        ? "No tumor mask results were saved before the run ended."
        : "Tumor masks are created after patients pass scan checks.";

  const controlId = useId();
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);
  const term = query.trim().toLowerCase();
  const visibleIds = term ? selectedIds.filter(id => id.toLowerCase().includes(term))
    : showAll ? selectedIds : selectedIds.slice(0, 3);
  const volumes = results.filter(result => result.status === "success" && typeof result.values.volume_cm3 === "number" && Number.isFinite(result.values.volume_cm3));

  return <section className="card results" aria-label="Tumor masks">
    <details className="result-disclosure">
      <summary><h2>Scans</h2><span>{qcResults.filter(result => result.status === "success").length} passed</span></summary>
    {!compact && <p className="result-finding">{finding}</p>}
    {!compact && !!results.length && <p className="result-caption">
      {ready} {ready === 1 ? "patient with a tumor mask" : "patients with tumor masks"}
      {failures ? ` · ${failures} mask construction ${failures === 1 ? "failure" : "failures"}` : ""}
    </p>}
    {(results.length > 0 || qcResults.length > 0) && <>
      <div className="result-search">
        <label htmlFor={controlId}>Search by patient ID</label>
        <input id={controlId} type="search" placeholder={selectedIds[0] ? `e.g. ${selectedIds[0]}` : undefined}
          value={query} onChange={event => setQuery(event.target.value)} aria-controls={`${controlId}-scans`} />
        <div className="result-actions">
          <span>or</span>
          <button type="button" className="primary" aria-controls={`${controlId}-scans`} aria-expanded={showAll && !term}
            onClick={() => { setShowAll(Boolean(term) || !showAll); setQuery(""); }}>
            {showAll && !term ? "Show fewer" : "View all"}
          </button>
        </div>
        <span role="status">{visibleIds.length ? `Showing ${visibleIds.length} of ${selectedIds.length} scans` : "No matching patients"}</span>
      </div>
      <div id={`${controlId}-scans`} className="patient-results scan-result-grid" tabIndex={0} role="region" aria-label="Patient tumor masks">
      {visibleIds.map(id => {
        const patient = results.find(r => r.patient_id === id);
        const qc = qcResults.find(r => r.patient_id === id);
        const excluded = qc && qc.status !== "success";
        const values = patient?.values;
        const overlay = patient?.artifacts?.find(a => a.role === "overlay" && a.media_type === "image/png" && (a.imageUrl || a.data_base64));
        const shape = values?.shape as number[] | undefined;
        const spacing = values?.spacing_mm as number[] | undefined;
        const ratio = shape && spacing ? shape[2] * spacing[2] / (shape[1] * spacing[1]) : 1;
        const volume = values?.volume_cm3;
        const voxelCount = values?.voxel_count;
        const sliceIndex = values?.slice_index;
        return <article key={id} className="patient-result">
          {(!compact || !overlay || patient?.status !== "success") && <div className="patient-heading"><strong>{id}</strong>
            <span className={`status ${excluded ? "failed" : patient?.status || (ended?"not-run":"pending")}`}>
              {excluded ? "Excluded by QC" : patient?.status || (ended?"Not run":"Pending")}
            </span>
          </div>}
          {patient?.status === "success" && values ? <>
            {(!compact || !overlay) && <p className="result-caption">
              {typeof volume === "number" && Number.isFinite(volume)
                ? `Tumor volume: ${volume.toLocaleString(undefined, { maximumFractionDigits: 3 })} cm³`
                : "Tumor volume unavailable"}
              {typeof voxelCount === "number" && Number.isFinite(voxelCount)
                ? ` · ${voxelCount.toLocaleString()} tumor voxels` : ""}
            </p>}
            {overlay ? <figure style={{ margin: "16px 0 0", maxWidth: 512 }}>
              <div className="scan-image" style={{ aspectRatio: ratio }}>
                {/* Bytes are owned by this result and remain usable after worker cleanup. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img tabIndex={0} aria-describedby={`${controlId}-scan-${id}`}
                  alt={`${id} tumor mask overlay on middle tumor-bearing CT slice`}
                  src={overlay.imageUrl ?? `data:image/png;base64,${overlay.data_base64}`} loading={overlay.imageUrl ? "lazy" : undefined}
                  style={{width: "100%", height: "100%", display: "block"}} />
                <div className="scan-tooltip" role="tooltip" id={`${controlId}-scan-${id}`}>
                  <p>The orange overlay marks the tumor.</p>
                  {compact && typeof volume === "number" && Number.isFinite(volume) && <p>Tumor volume: {volume.toLocaleString(undefined, {maximumFractionDigits: 3})} cm³</p>}
                  {typeof voxelCount === "number" && <p>{voxelCount.toLocaleString()} tumor voxels</p>}
                  {spacing && <p>Spacing (slice × row × column) {spacing.map(n => n.toLocaleString(undefined, {maximumFractionDigits: 5})).join(" × ")} mm</p>}
                  {typeof sliceIndex === "number" && shape && <p>Middle tumor-bearing slice {sliceIndex + 1} of {shape[0]}. Lung window −1000 to 400 HU.</p>}
                </div>
              </div>
              <figcaption className="scan-figure-caption">
                <span>{id}</span>
                {typeof volume === "number" && Number.isFinite(volume) && <span>{volume.toLocaleString(undefined, {maximumFractionDigits: 3})} cm³</span>}
              </figcaption>
            </figure> : <p className="muted">No overlay image is available for this result.</p>}
            {!overlay && spacing && <details className="scan-caption">
              <summary>Scan details</summary>
              <p>Spacing (slice × row × column) {spacing.map(n => n.toLocaleString(undefined, {maximumFractionDigits: 5})).join(" × ")} mm</p>
            </details>}
          </> : <p className={patient?.errors.length ? "error-text" : "muted"}>
            {patient?.errors.length ? patient.errors.map(e => e.message).join("; ") : excluded ? "This patient did not pass scan checks and was not sent to mask construction." : ended ? "No mask result was saved before the run ended." : "Waiting for mask construction after scan checks…"}
          </p>}
        </article>;
      })}
    </div></>}
    {children}
    {volumes.length > 0 && <details className="result-inner-details">
      <summary>View tumor volumes</summary>
      <table className="result-list-table"><thead><tr><th scope="col">Patient</th><th scope="col">Volume</th></tr></thead>
        <tbody>{volumes.map(patient => <tr key={patient.patient_id}><th scope="row">{patient.patient_id}</th><td>
          {(patient.values.volume_cm3 as number).toLocaleString(undefined, {maximumFractionDigits: 3})} cm³
        </td></tr>)}</tbody>
      </table>
    </details>}
    </details>
  </section>;
}
