"""Generate immutable product examples through the public run API, never reference features.

Faults exist only in a disposable library. This command does not change the catalog,
source DICOMs, frozen model or full held-out evaluation. See docs/ticket-14-handoff.md.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import httpx


def export(snapshot, label, description, faults):
    """Keep result bytes and disclosure, remove every visitor control capability."""
    forbidden = {'secret', 'launch_nonce', 'worker_context', 'checkpoint', 'disclosure_id',
                 'signature', 'token', 'checkpoint_token', 'approved_disclosure'}
    def clean(value):
        if isinstance(value, dict):
            return {k:clean(v) for k,v in value.items() if k not in forbidden and k not in {'path','url'}}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    events = clean(snapshot['events'])
    for event in events:
        event['id'] = f"{label}:{event['sequence']}"
        event['run_id'] = label
    return {'version':1,'id':label,'patientIds':snapshot['patient_ids'],
            'status':snapshot['status'],'createdAt':events[0]['timestamp'],
            'events':events,'description':description,'faults':faults,
            'provenance':{'execution':'Actual public run API and imaging tools',
                          'model_version':snapshot['model']['model_version'],
                          'evaluation_version':snapshot['model']['evaluation']['evaluation_version'],
                          'export':'Terminal read-only product asset; no visitor control capability'}}


def capture(raw, outcomes, bundle, output, label, description, faults, ports):
    engine, runner = ports
    env = {**os.environ,'RAW_DIR':str(raw),'OUTCOMES_CSV':str(outcomes),'MODEL_BUNDLE':str(bundle),
           'ENGINE_SECRET':'isolated-curation-only','ENGINE_URL':f'http://127.0.0.1:{engine}',
           'CHECKPOINT_SIGNING_KEY':'isolated-product-curation-signing-key-not-deployed',
           'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'1',
           'ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS':'1'}
    processes = []
    try:
        for module, port in [('service.engine_api:app',engine),('service.app:app',runner)]:
            processes.append(subprocess.Popen([sys.executable,'-m','uvicorn',module,'--port',str(port)],env=env,stdout=subprocess.DEVNULL))
        with httpx.Client(base_url=f'http://127.0.0.1:{runner}',timeout=30) as client:
            for _ in range(200):
                try: client.get('/'); break
                except httpx.ConnectError: time.sleep(.1)
            selected = ['LUNG1-002','LUNG1-009'] + (['LUNG1-015'] if faults else [])
            response = client.post('/runs',json={'patient_ids':selected}); response.raise_for_status()
            run = response.json()
            headers = {'Authorization':f"Bearer {run['secret']}"}
            approved = False
            for _ in range(1200):
                response = client.get(f"/runs/{run['id']}",headers=headers); response.raise_for_status()
                snapshot = response.json()
                if snapshot['status'] == 'waiting_approval' and not approved:
                    gate = snapshot['checkpoint']
                    response = client.post(f"/runs/{run['id']}/approve",headers=headers,
                                           json={k:gate[k] for k in ['disclosure_id','model_version']})
                    response.raise_for_status(); approved = True
                if snapshot['status'] in ['completed','failed','canceled']: break
                time.sleep(.25)
            assert snapshot['status'] == 'completed', snapshot
            assert approved == bool(faults)
            result = export(snapshot,label,description,faults)
            output.mkdir(parents=True,exist_ok=True)
            (output/f'{label}.json').write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
            print(f"{label}: {len(result['events'])} actual ordered events; {len(snapshot['stage_results']['score'])} scored",flush=True)
    finally:
        for process in processes: process.terminate()
        for process in processes:
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('web/public/examples'))
    parser.add_argument('--engine-port',type=int,default=8141)
    parser.add_argument('--runner-port',type=int,default=8140)
    args = parser.parse_args()
    ports = (args.engine_port,args.runner_port)
    capture(args.prepared/'raw',args.prepared/'outcomes.csv',args.bundle,args.output,'curated-success',
            'Curated success · actual execution',[],ports)
    with tempfile.TemporaryDirectory(prefix='mini-nota-curated-fault-') as directory:
        root = Path(directory)
        for patient in ['LUNG1-002','LUNG1-009']:
            shutil.copytree(args.prepared/'raw'/patient,root/patient,copy_function=os.link)
        # A new file, never a mutation of a source hard link.
        (root/'LUNG1-015'/'ct').mkdir(parents=True)
        (root/'LUNG1-015'/'ct'/'malformed.dcm').write_bytes(b'explicit malformed DICOM fixture')
        import pandas as pd
        outcomes = pd.read_csv(args.prepared/'outcomes.csv')
        outcomes[outcomes.patient_id != 'LUNG1-002'].to_csv(root/'outcomes.csv',index=False)
        capture(root,root/'outcomes.csv',args.bundle,args.output,'curated-failure',
                'Failure-path fixture · actual execution with deliberately introduced faults',
                ['LUNG1-015: synthetic malformed DICOM replaces this patient only in a temporary library.',
                 'LUNG1-002: outcome deliberately removed from a temporary CSV; still scored, excluded only from selected-cohort evaluation.'],ports)

if __name__ == '__main__': main()
