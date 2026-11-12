import type { MaskPatientResult } from './MaskResults';

export default function QCResults({selectedIds,results,ended=false}:{selectedIds:string[];results:MaskPatientResult[];ended?:boolean}) {
  return <section className="card results" aria-label="Scan quality">
    <div className="card-heading"><div><h2>Scan quality</h2><p>Geometry, slice spacing, and anonymization</p></div><span>{results.length} / {selectedIds.length} checked</span></div>
    {!results.length ? <p className="stage-empty">{ended?'No scan checks were saved before the run ended.':'Scan checks appear as patients finish QC.'}</p> : <div className="patient-results" tabIndex={0} role="region" aria-label="Patient scan checks">{selectedIds.map(id=>{
      const result=results.find(r=>r.patient_id===id);
      return <article className="patient-result" key={id}><div className="patient-heading"><strong>{id}</strong><span className={`status ${result?.status||'pending'}`}>{result?.status||(ended?'Not checked':'Pending')}</span></div>
        {result ? <><div className="checks">{['geometry','slice_spacing','anonymized'].map(check=>{const value=result.values[check] as {passed:boolean;detail:string}|undefined;return <div key={check}><small>{check.replace('_',' ')}</small><strong className={value?.passed?'pass':'fail'}>{value?(value.passed?'✓ Passed':'! Flagged'):'Unavailable'}</strong><p>{value?.detail}</p></div>})}</div>{result.errors.map((error,i)=><p className="error-text" key={i}>{error.message}</p>)}</> : <p className="muted">{ended?'No QC result saved before the run ended.':'Waiting for scan checks…'}</p>}
      </article>
    })}</div>}
  </section>;
}
