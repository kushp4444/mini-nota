"""Deploy only after human account/budget setup; importing does not deploy.

Stage the reviewed manifest at deploy/worker-manifest.json (ignored by Git).
No raw scans, model bundle, credentials or generated runs enter either image.
"""
import os
import modal

app = modal.App(os.environ.get('MODAL_APP_NAME','mini-nota'))
worker_image = modal.Image.from_dockerfile('deploy/Dockerfile.modal', context_dir='.')
dispatcher_image = modal.Image.from_dockerfile('deploy/Dockerfile.dispatcher', context_dir='.').entrypoint([])


@app.function(image=worker_image, secrets=[modal.Secret.from_name('mini-nota-worker')],
    cpu=(1, 1), memory=(4096, 6144), ephemeral_disk=16384,
    timeout=1800, startup_timeout=600, retries=0, min_containers=0,
    max_containers=2, buffer_containers=0, scaledown_window=2,
    single_use_containers=True)
async def run_phase(operation_id: str):
    from service.modal_worker import run_phase as execute
    # Actual provider ID is obtained inside the input, never trusted from a caller.
    try:
        return await execute(operation_id, modal.current_function_call_id())
    except Exception:
        # A bootstrap DB outage has not loaded scans; provider completion will
        # reconcile to an explicit interruption when the repository recovers.
        # Never send credentials, CT bytes or exception details to call output.
        return {'status':'bootstrap_failed'}


# Manual bounded reconciliation, deliberately NO schedule/idle database polling.
# Startup and authorized active controls/reconnects also reconcile committed intent.
@app.function(image=dispatcher_image, secrets=[modal.Secret.from_name('mini-nota-reconciler')],
    cpu=(.125, .25), memory=(256, 512), timeout=90, retries=0,
    min_containers=0, max_containers=1, buffer_containers=0)
async def reconcile_pending():
    from service.run_repository import RunRepository
    from service.execution import ModalProvider, reconcile
    await reconcile(RunRepository(os.environ['RUN_DATABASE_URL']), ModalProvider())
    return {'status':'reconciled'}
