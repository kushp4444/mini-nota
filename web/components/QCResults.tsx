import type { MaskPatientResult } from "./MaskResults";

const checks = [
  { key: "geometry", label: "Scan geometry" },
  { key: "slice_spacing", label: "Slice spacing" },
  { key: "anonymized", label: "Anonymization" },
];

type ScanCheck = { passed: boolean; detail: string };

function checkValue(result: MaskPatientResult, key: string) {
  return result.values[key] as ScanCheck | undefined;
}

function flagged(result: MaskPatientResult) {
  return result.status !== "success" && checkValue(result, "anonymized")?.passed === false;
}

function excluded(result: MaskPatientResult) {
  return result.status !== "success";
}

export default function QCResults({ selectedIds, results, ended = false }: {
  selectedIds: string[];
  results: MaskPatientResult[];
  ended?: boolean;
}) {
  const passed = results.filter(result => !excluded(result)).length;
  const flags = results.filter(flagged).length;
  const failures = results.length - passed - flags;
  const unchecked = selectedIds.length - results.length;
  const finding = passed
    ? `${passed} ${passed === 1 ? "patient" : "patients"} passed scan checks and could continue to mask construction.`
    : results.length
      ? "No patients passed scan checks, so mask construction could not proceed for those checked."
      : ended
        ? "No scan checks were saved before the run ended."
        : "Scan checks determine which patients can continue to mask construction.";

  return <section className="card results" aria-label="Scan quality">
    <div className="card-heading"><h2>Scan quality</h2></div>
    <p className="result-finding">{finding}</p>
    <p className="result-caption">
      {[
        `${results.length} of ${selectedIds.length} patients checked`,
        flags ? `${flags} anonymization ${flags === 1 ? "flag" : "flags"}` : null,
        failures ? `${failures} processing ${failures === 1 ? "failure" : "failures"}` : null,
        ended && unchecked > 0 ? `${unchecked} without a saved check` : null,
      ].filter(Boolean).join(" · ")}
    </p>
    {results.some(excluded) && <div className="patient-results" tabIndex={0} role="region" aria-label="Patients excluded by scan checks">
      {results.filter(excluded).map(result => (
        <article className="patient-result" key={result.patient_id}>
          <div className="patient-heading">
            <strong>{result.patient_id}</strong>
            <span className="status failed">{flagged(result) ? "Flagged by anonymization check" : "Processing failure"}</span>
          </div>
          {checks.map(({ key, label }) => {
            const value = checkValue(result, key);
            return value?.passed === false && value.detail
              ? <p key={key}>{label} — {value.detail}</p>
              : null;
          })}
          {result.errors.map((error, index) => <p className="error-text" key={index}>{error.message}</p>)}
          <p className="muted">This patient could not continue to mask construction.</p>
        </article>
      ))}
    </div>}
    {!!results.length && <details className="result-details">
      <summary>View details</summary>
      <div className="patient-results" tabIndex={0} role="region" aria-label="Patient scan checks">
        {selectedIds.map(id => {
          const result = results.find(item => item.patient_id === id);
          return <article className="patient-result" key={id}>
            <div className="patient-heading">
              <strong>{id}</strong>
              <span className={`status ${result?.status || "pending"}`}>
                {result?.status || (ended ? "Not checked" : "Pending")}
              </span>
            </div>
            {result ? <div className="checks">
              {checks.map(({ key, label }) => {
                const value = checkValue(result, key);
                return <div key={key}>
                  <small>{label}</small>
                  <strong className={value?.passed ? "pass" : "fail"}>
                    {value ? (value.passed ? "✓ Passed" : "Failed") : "Unavailable"}
                  </strong>
                  <p>{value?.detail}</p>
                </div>;
              })}
            </div> : <p className="muted">{ended ? "No scan result saved before the run ended." : "Waiting for scan checks…"}</p>}
          </article>;
        })}
      </div>
    </details>}
  </section>;
}
