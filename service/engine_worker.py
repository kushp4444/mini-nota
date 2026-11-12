"""One isolated engine operation; owned and terminated by the private HTTP service."""
import base64
from contextlib import redirect_stdout
import json
import sys
from src.engine import EngineWorkspace


def main():
    request = json.load(sys.stdin)
    # Numerical libraries may print diagnostics; stdout is the structured contract.
    with redirect_stdout(sys.stderr):
        with EngineWorkspace(request['raw_dir'], request['workspace']) as engine:
            result = engine.run_stage(request['stage'], request['patient_ids'])
            for patient in result['patients']:
                retained = []
                for artifact in patient['artifacts']:
                    if artifact.get('role') == 'mask':
                        continue
                    data = (engine.path / artifact['path']).read_bytes()
                    retained.append({**artifact, 'data_base64': base64.b64encode(data).decode('ascii')})
                patient['artifacts'] = retained
    json.dump(result, sys.stdout)


if __name__ == '__main__':
    main()
