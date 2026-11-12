"""Release entrypoint through its public engine HTTP boundary; synthetic slow tool."""
import concurrent.futures
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import httpx
import pytest


def available_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_for(predicate, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError('Timed out waiting for owned service state')


def alive(pid):
    try:
        os.kill(pid, 0)
        # Linux zombies have stopped execution and await reaping.
        stat = Path(f'/proc/{pid}/stat')
        return not (stat.exists() and stat.read_text().split()[2] == 'Z')
    except ProcessLookupError:
        return False


@pytest.mark.parametrize('lost', ['runner', 'engine', 'supervisor', 'stop'])
def test_backend_unit_stops_detached_tools_and_cleans_temporary_files(tmp_path, lost):
    runner_port, engine_port = available_port(), available_port()
    (tmp_path/'release_slow_fixture.py').write_text('''import json,os,sys,time\nfrom pathlib import Path\nr=json.load(sys.stdin)\nPath(os.environ['MARKER']).write_text(json.dumps({'pid':os.getpid(),'workspace':r['workspace']}))\ntime.sleep(120)\n''')
    marker = tmp_path/'started.json'
    env = {**os.environ, 'PORT':str(runner_port),'ENGINE_PORT':str(engine_port),
           'ENGINE_SECRET':'local-fixture-secret','CHECKPOINT_SIGNING_KEY':'local-unit-fixture-'+'x'*48,
           'RAW_DIR':str(tmp_path), 'TMPDIR':str(tmp_path), 'MARKER':str(marker),
           'PYTHONPATH':str(tmp_path), 'ENGINE_WORKER_MODULE':'release_slow_fixture'}
    proc = subprocess.Popen([sys.executable, '-m', 'service.backend'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def ready():
        try:
            return httpx.get(f'http://127.0.0.1:{runner_port}/runs/launch-context',timeout=.2).status_code == 200
        except httpx.HTTPError:
            return False
    def request():
        try:
            return httpx.post(f'http://127.0.0.1:{engine_port}/qc',headers={'Authorization':'Bearer local-fixture-secret'},json={'patient_ids':['FIXTURE']},timeout=15)
        except httpx.HTTPError:
            return None
    try:
        wait_for(ready)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = pool.submit(request)
            wait_for(marker.exists)
            tool = json.loads(marker.read_text())
            assert alive(tool['pid']) and Path(tool['workspace']).exists()
            if lost in ('supervisor','stop'):
                proc.send_signal(signal.SIGTERM if lost == 'stop' else signal.SIGKILL)
            else:
                children = subprocess.check_output(['ps','-axo','pid=,ppid=,command='],text=True).splitlines()
                service = next(int(line.split()[0]) for line in children if len(line.split())>2 and int(line.split()[1])==proc.pid and f'service.{"app" if lost=="runner" else "engine_api"}:app' in line)
                os.kill(service,signal.SIGKILL)
            proc.wait(timeout=15)
            wait_for(lambda:not alive(tool['pid']))
            result.result(timeout=15)
            if lost != 'supervisor':
                assert not Path(tool['workspace']).exists()
                assert not list(tmp_path.glob('mini-nota-unit-*'))
            # SIGKILL PID1 cannot execute filesystem cleanup; Linux tmpfs/container
            # disposal owns that case. Detached computation still stops on EOF.
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=15)
