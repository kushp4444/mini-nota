"use client";

export type MaskPatientResult = {
  patient_id: string;
  status: string;
  values: Record<string, unknown>;
  errors: { code?: string; message: string }[];
  artifacts?: { role?: string; media_type: string; data_base64?: string }[];
};

/** Render retained stage values and bytes; no expiring server URLs. */
export default function MaskResults({ selectedIds, results, qcResults, ended=false }: {
  selectedIds: string[];
  results: MaskPatientResult[];
  qcResults: MaskPatientResult[];
  ended?:boolean;
}) {
  return <div className="card results" aria-label="Tumor masks">
    <div className="card-heading">
      <div><h2>Tumor masks</h2><p>Verified CT geometry · physical tumor volume</p></div>
      <span>{results.filter(r => r.status === "success").length} masks ready</span>
    </div>
    {!results.length && !qcResults.length ? <p className="stage-empty">Tumor measurements and overlays appear after scan checks.</p> : <div className="patient-results" tabIndex={0} role="region" aria-label="Patient tumor masks">
      {selectedIds.map(id => {
        const patient = results.find(r => r.patient_id === id);
        const qc = qcResults.find(r => r.patient_id === id);
        const excluded = qc && qc.status !== "success";
        const values = patient?.values;
        const overlay = patient?.artifacts?.find(a => a.role === "overlay" && a.media_type === "image/png" && a.data_base64);
        const shape = values?.shape as number[] | undefined;
        const spacing = values?.spacing_mm as number[] | undefined;
        const ratio = shape && spacing ? shape[2] * spacing[2] / (shape[1] * spacing[1]) : 1;
        return <article key={id} className="patient-result">
          <div className="patient-heading"><strong>{id}</strong>
            <span className={`status ${excluded ? "failed" : patient?.status || (ended?"not-run":"pending")}`}>
              {excluded ? "Excluded by QC" : patient?.status || (ended?"Not run":"Pending")}
            </span>
          </div>
          {patient?.status === "success" && values ? <>
            <div className="checks">
              <div><small>Tumor voxels</small><strong>{Number(values.voxel_count).toLocaleString()}</strong></div>
              <div><small>Tumor volume</small><strong>{Number(values.volume_cm3).toLocaleString(undefined, { maximumFractionDigits: 3 })} cm³</strong></div>
              <div><small>Spacing (slice × row × column)</small><strong>{spacing?.map(n => n.toLocaleString(undefined, { maximumFractionDigits: 5 })).join(" × ")} mm</strong></div>
            </div>
            {overlay ? <figure style={{ margin: "16px 0 0", maxWidth: 512 }}>
              <div style={{ aspectRatio: ratio, background: "#000" }}>
                {/* Bytes are owned by this result and remain usable after worker cleanup. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img alt={`${id} tumor mask overlay on middle tumor-bearing CT slice`} src={`data:image/png;base64,${overlay.data_base64}`} style={{ width: "100%", height: "100%", display: "block" }} />
              </div>
              <figcaption className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                Middle tumor-bearing slice {Number(values.slice_index) + 1} of {shape?.[0]} · orange: tumor · native CT plane · lung window −1000 to 400 HU
              </figcaption>
            </figure> : <p className="error-text">Overlay bytes are unavailable for this result.</p>}
          </> : <p className={patient?.errors.length ? "error-text" : "muted"}>
            {patient?.errors.length ? patient.errors.map(e => e.message).join("; ") : excluded ? "This patient did not pass scan checks and was not sent to mask construction." : ended ? "No mask result was saved before the run ended." : "Waiting for mask construction after scan checks…"}
          </p>}
        </article>;
      })}
    </div>}
  </div>;
}
