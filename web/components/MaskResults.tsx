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
  const ready = results.filter(result => result.status === "success").length;
  const failures = results.length - ready;
  const finding = ready
    ? ready === 1 ? "A tumor mask was created from the CT scan." : "Tumor masks were created from the CT scans."
    : results.length
      ? "Mask construction did not produce a tumor mask."
      : ended
        ? "No tumor mask results were saved before the run ended."
        : "Tumor masks are created after patients pass scan checks.";

  return <section className="card results" aria-label="Tumor masks">
    <div className="card-heading"><h2>Tumor masks</h2></div>
    <p className="result-finding">{finding}</p>
    {!!results.length && <p className="result-caption">
      {ready} {ready === 1 ? "patient with a tumor mask" : "patients with tumor masks"}
      {failures ? ` · ${failures} mask construction ${failures === 1 ? "failure" : "failures"}` : ""}
    </p>}
    {results.length || qcResults.length ? <div className="patient-results" tabIndex={0} role="region" aria-label="Patient tumor masks">
      {selectedIds.map(id => {
        const patient = results.find(r => r.patient_id === id);
        const qc = qcResults.find(r => r.patient_id === id);
        const excluded = qc && qc.status !== "success";
        const values = patient?.values;
        const overlay = patient?.artifacts?.find(a => a.role === "overlay" && a.media_type === "image/png" && a.data_base64);
        const shape = values?.shape as number[] | undefined;
        const spacing = values?.spacing_mm as number[] | undefined;
        const ratio = shape && spacing ? shape[2] * spacing[2] / (shape[1] * spacing[1]) : 1;
        const volume = values?.volume_cm3;
        const voxelCount = values?.voxel_count;
        const sliceIndex = values?.slice_index;
        return <article key={id} className="patient-result">
          <div className="patient-heading"><strong>{id}</strong>
            <span className={`status ${excluded ? "failed" : patient?.status || (ended?"not-run":"pending")}`}>
              {excluded ? "Excluded by QC" : patient?.status || (ended?"Not run":"Pending")}
            </span>
          </div>
          {patient?.status === "success" && values ? <>
            <p className="result-caption">
              {typeof volume === "number" && Number.isFinite(volume)
                ? `Tumor volume: ${volume.toLocaleString(undefined, { maximumFractionDigits: 3 })} cm³`
                : "Tumor volume unavailable"}
              {typeof voxelCount === "number" && Number.isFinite(voxelCount)
                ? ` · ${voxelCount.toLocaleString()} tumor voxels` : ""}
            </p>
            {overlay ? <figure style={{ margin: "16px 0 0", maxWidth: 512 }}>
              <div style={{ aspectRatio: ratio, background: "#000" }}>
                {/* Bytes are owned by this result and remain usable after worker cleanup. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img alt={`${id} tumor mask overlay on middle tumor-bearing CT slice`} src={`data:image/png;base64,${overlay.data_base64}`} style={{ width: "100%", height: "100%", display: "block" }} />
              </div>
              <figcaption className="result-caption">The orange overlay shows the tumor on a CT slice.</figcaption>
            </figure> : <p className="muted">No overlay image is available for this result.</p>}
            {(spacing || (overlay && typeof sliceIndex === "number" && shape)) && <details className="result-details">
              <summary>View details</summary>
              {spacing && <p>Spacing (slice × row × column) {spacing.map(n => n.toLocaleString(undefined, { maximumFractionDigits: 5 })).join(" × ")} mm</p>}
              {overlay && typeof sliceIndex === "number" && shape && <p>
                Middle tumor-bearing slice {sliceIndex + 1} of {shape[0]} · native CT plane · lung window −1000 to 400 HU
              </p>}
            </details>}
          </> : <p className={patient?.errors.length ? "error-text" : "muted"}>
            {patient?.errors.length ? patient.errors.map(e => e.message).join("; ") : excluded ? "This patient did not pass scan checks and was not sent to mask construction." : ended ? "No mask result was saved before the run ended." : "Waiting for mask construction after scan checks…"}
          </p>}
        </article>;
      })}
    </div> : null}
  </section>;
}
