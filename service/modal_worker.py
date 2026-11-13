"""Phase-sized remote execution. No native import or source bytes before claim."""
import asyncio
import os
import uuid
from .run_repository import RunRepository, Conflict


async def run_phase(operation_id, provider_call_id, *, assets=None, source_client=None, source_bucket=None):
    if not isinstance(provider_call_id,str) or not provider_call_id:
        raise ValueError('A real provider FunctionCall identity is required')
    repo = RunRepository(os.environ['RUN_DATABASE_URL'])
    attempt_id = str(uuid.uuid4())
    fence = repo.claim(operation_id, provider_call_id, attempt_id=attempt_id)
    if fence is None:
        return {'status':'skipped'}
    # A repeated input, even with the SAME FunctionCall ID, cannot claim again.
    context = repo.operation_context(operation_id)
    run = context['run']
    operation = {'id':operation_id, 'owner':provider_call_id, 'fence':fence, 'attempt_id':attempt_id}
    run['_operation'] = operation
    from . import app as policy

    def check_owned():
        if not repo.owns(operation):
            raise Conflict('Phase ownership ended')

    async def watch_cancel(task):
        while not task.done():
            await asyncio.sleep(.5)
            try:
                check_owned()
            except Exception:
                # Fail closed on DB outage too; no unowned native computation.
                task.cancel()
                return

    token = None
    watcher = None
    try:
        check_owned()
        from .asset_storage import TrustedAssets
        from .object_storage import client_from_env
        from .native_tools import NativeTools
        if assets is None:
            assets = TrustedAssets(os.environ['ASSET_MANIFEST'], os.environ['ASSET_MANIFEST_SHA256'])
            source_client = client_from_env('assets')
            source_bucket = os.environ['R2_ASSETS_BUCKET']
        # Downloaded bytes remain worker-local; ownership is checked again
        # before any native computation. Provider cancellation kills transfers.
        selected = assets.selected(source_client, source_bucket, run['patient_ids'], scans=context['phase'] == 'imaging')
        with selected as root:
            check_owned()
            async with NativeTools(root, check_owned) as tools:
                token = policy.tool_transport.set(tools)
                task = asyncio.create_task(policy.execute(run) if context['phase'] == 'imaging' else policy.score_run(run, policy.checkpoint_rows(run['checkpoint'])))
                watcher = asyncio.create_task(watch_cancel(task))
                await task
        return {'status':repo.get(run['id'])['status']}
    except (Conflict, asyncio.CancelledError):
        return {'status':'stopped'}
    except Exception:
        # Source/native initialization failure retains every committed earlier
        # result. Publication still requires the exact uncanceled fence.
        try:
            saved = repo.get(run['id'])
            saved['_operation'] = operation
            saved['status'] = 'failed'
            policy.emit(saved, 'error', 'Remote execution failed; available results retained.', {'code':'remote_execution_failed'})
            policy.emit(saved, 'done', 'Run failed.', {'status':'failed','reason':'Remote execution failed.'})
        except Conflict:
            return {'status':'stopped'}
        return {'status':'failed'}
    finally:
        if watcher is not None:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        if token is not None:
            policy.tool_transport.reset(token)
