"""Explicit slow subprocess fixture, never used for library measurements."""
import json
import os
from pathlib import Path
import sys
import time
request = json.load(sys.stdin)
root = Path(request['raw_dir'])
if request['stage'] == os.environ.get('SLOW_ENGINE_STAGE', 'qc'):
    (root / 'started.json').write_text(json.dumps({'pid': os.getpid(), 'workspace': request['workspace']}))
    time.sleep(3)
    (root / 'finished').write_text('The slow tool completed')
json.dump({'patients': [{'patient_id': request['patient_ids'][0], 'status': 'success', 'values': {}, 'errors': [], 'artifacts': []}]}, sys.stdout)
