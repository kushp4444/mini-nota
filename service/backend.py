"""One ephemeral backend unit. Run as container PID1: python -m service.backend.

A pipe held only by this supervisor is the lifetime capability for every tool.
EOF stops detached groups even when the owning engine is killed abruptly; no
PID scanning or stale PID ledger can signal an unrelated host process.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def main():
    if len(os.environ.get('CHECKPOINT_SIGNING_KEY', '')) < 32 or not os.environ.get('ENGINE_SECRET'):
        raise SystemExit('Configure stable CHECKPOINT_SIGNING_KEY and private ENGINE_SECRET')
    if os.environ.get('ASSET_MANIFEST'):
        from scripts.release_assets import verify
        manifest = Path(os.environ['ASSET_MANIFEST'])
        root = manifest.parent
        verify(root, manifest, os.environ.get('ASSET_MANIFEST_SHA256',''))
        for name, relative in [('RAW_DIR','raw'),('MODEL_BUNDLE','model.json'),('OUTCOMES_CSV','outcomes.csv')]:
            if Path(os.environ.get(name,'')).resolve() != (root/relative).resolve():
                raise SystemExit('Backend asset paths must match the validated immutable release')
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Linux PID1 adopts descendants automatically. Subreaper also allows this
    # entrypoint's integration tests to reap orphaned tools outside containers.
    if sys.platform == 'linux':
        import ctypes
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
            raise RuntimeError('Cannot establish backend descendant ownership')
    reader, writer = os.pipe()
    services = []
    result = 1
    with tempfile.TemporaryDirectory(prefix='mini-nota-unit-') as temporary:
        env = {**os.environ, 'TMPDIR':temporary, 'MPLCONFIGDIR':str(Path(temporary)/'matplotlib'),
               'XDG_CACHE_HOME':str(Path(temporary)/'cache'), 'MINI_NOTA_LIFETIME_FD':str(reader),
               'ENGINE_URL':f"http://127.0.0.1:{os.environ.get('ENGINE_PORT','8001')}"}
        try:
            for module, host, port in [('service.engine_api:app','127.0.0.1',os.environ.get('ENGINE_PORT','8001')),
                                       ('service.app:app',os.environ.get('RUNNER_HOST','0.0.0.0'),os.environ.get('PORT','8000'))]:
                services.append(subprocess.Popen([sys.executable,'-m','uvicorn',module,'--host',host,'--port',port,'--no-access-log'],env=env,pass_fds=(reader,)))
            os.close(reader)
            reader = None
            while not stopping and all(proc.poll() is None for proc in services):
                time.sleep(.05)
            result = 0 if stopping else 1  # Any service exit stops the unit, even exit 0.
        finally:
            os.close(writer)  # Detached tool watchdogs stop their own groups.
            if reader is not None:
                os.close(reader)
            for proc in services:
                if proc.poll() is None:
                    proc.terminate()
            deadline = time.monotonic() + 5
            for proc in services:
                try:
                    proc.wait(timeout=max(.01,deadline-time.monotonic()))
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if sys.platform == 'linux':
                # Reap adopted killed tools before cleaning their shared tmpfs tree.
                while True:
                    try:
                        pid, _ = os.waitpid(-1, os.WNOHANG)
                    except ChildProcessError:
                        break
                    if not pid:
                        if time.monotonic() > deadline:
                            break
                        time.sleep(.02)
            else:
                time.sleep(.2)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
