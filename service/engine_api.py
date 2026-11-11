"""Private engine service. Bind loopback or protect with ENGINE_SECRET externally."""
import os
import base64
import tempfile
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from src.engine import EngineWorkspace

app = FastAPI(docs_url=None, redoc_url=None)
class Selection(BaseModel):
    patient_ids: list[str]

@app.post('/qc')
def qc(selection: Selection, authorization: str = Header(default='')):
    return run_stage('qc', selection, authorization)

@app.post('/masks')
def masks(selection: Selection, authorization: str = Header(default='')):
    return run_stage('masks', selection, authorization)

def run_stage(stage, selection, authorization):
    secret = os.environ.get('ENGINE_SECRET')
    if not secret or authorization != f'Bearer {secret}':
        raise HTTPException(403, 'Engine access denied')
    with EngineWorkspace(os.environ['RAW_DIR'], tempfile.gettempdir()) as engine:
        result = engine.run_stage(stage, selection.patient_ids)
        for patient in result['patients']:
            retained = []
            for artifact in patient['artifacts']:
                # The raw working mask is large and private; retain the display PNG.
                if artifact.get('role') == 'mask':
                    continue
                data = (engine.path / artifact['path']).read_bytes()
                retained.append({**artifact, 'data_base64': base64.b64encode(data).decode('ascii')})
            patient['artifacts'] = retained
        return result
