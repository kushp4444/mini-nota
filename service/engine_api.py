"""Private engine service. Bind loopback or protect with ENGINE_SECRET externally."""
import os
import tempfile
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from src.engine import EngineWorkspace

app = FastAPI(docs_url=None, redoc_url=None)
class Selection(BaseModel):
    patient_ids: list[str]

@app.post('/qc')
def qc(selection: Selection, authorization: str = Header(default='')):
    secret = os.environ.get('ENGINE_SECRET')
    if not secret or authorization != f'Bearer {secret}':
        raise HTTPException(403, 'Engine access denied')
    with EngineWorkspace(os.environ['RAW_DIR'], tempfile.gettempdir()) as engine:
        return engine.run_stage('qc', selection.patient_ids)
