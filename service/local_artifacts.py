"""Explicit development-only durable artifact store; production uses R2."""
import hashlib
from pathlib import Path


class LocalArtifactStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def publish(self, run_id, artifact_id, data, media_type):
        digest = hashlib.sha256(data).hexdigest()
        if len(data) > 4_000_000:
            raise ValueError('Artifact exceeds delivery bound')
        key = hashlib.sha256(f'{run_id}:{artifact_id}:{digest}'.encode()).hexdigest()
        path = self.root / key
        path.write_bytes(data)
        path.chmod(0o600)
        return {'storage':'local','run_id':run_id,'artifact_id':artifact_id,'key':key,
                'sha256':digest,'size_bytes':len(data),'media_type':media_type}

    def read(self, run_id, reference):
        if reference['run_id'] != run_id or not isinstance(reference['key'],str) or len(reference['key']) != 64 or any(c not in '0123456789abcdef' for c in reference['key']):
            raise ValueError('Invalid artifact ownership')
        with (self.root / reference['key']).open('rb') as source:
            data = source.read(4_000_001)
        if len(data) != reference['size_bytes'] or hashlib.sha256(data).hexdigest() != reference['sha256']:
            raise ValueError('Artifact integrity check failed')
        return data
