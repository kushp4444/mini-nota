"""Worker-local structured native tools with private process-group ownership.

The lifetime pipe belongs to one phase input, not the dispatcher or a reusable
container global. Abrupt owner death closes it; tool_entry kills its own group.
"""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import tempfile

import httpx


class NativeTools:
    def __init__(self, root, check_owned):
        self.root = Path(root)
        self.check_owned = check_owned
        self.reader, self.writer = os.pipe()
        self.process = None

    async def __aenter__(self):
        return self

    async def stop(self):
        if self.process is not None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await self.process.wait()
            self.process = None

    async def __aexit__(self, *exc):
        os.close(self.writer)
        await self.stop()
        os.close(self.reader)

    async def call(self, stage, selection):
        self.check_owned()
        with tempfile.TemporaryDirectory(prefix='mini-nota-native-') as workspace:
            env = {**os.environ, 'MINI_NOTA_LIFETIME_FD':str(self.reader),
                   'MODEL_BUNDLE':str(self.root/'model.json'), 'OUTCOMES_CSV':str(self.root/'outcomes.csv')}
            for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','VECLIB_MAXIMUM_THREADS','ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'):
                env[name] = '1'
            # Production assets have raw/; explicit local test source may supply
            # raw_dir separately without changing any production source contract.
            request = {**selection, 'stage':stage, 'raw_dir':str(self.root/'raw'), 'workspace':workspace}
            try:
                self.process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'service.tool_entry',
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
                    env=env, pass_fds=(self.reader,))
                stdout, _ = await self.process.communicate(json.dumps(request).encode())
                self.check_owned()
                if self.process.returncode:
                    raise RuntimeError('Native tool stopped without a result')
                result = json.loads(stdout)
                if stage in ('eligibility','score') and result.get('errors'):
                    response = httpx.Response(422, json={'detail':result['errors']}, request=httpx.Request('POST','http://worker/'+stage))
                    response.raise_for_status()
                return result
            finally:
                await self.stop()

    async def patient(self, stage, patient_id, run_id):
        return (await self.call(stage, {'patient_ids':[patient_id]}))['patients'][0]

    async def model(self, stage, run, rows):
        return await self.call(stage, {'patient_ids':[r['patient_id'] for r in rows], 'feature_rows':rows,
            'model_version':run['model']['model_version'],
            'expected_eligibility':run['eligibility'] if stage == 'score' else None})
