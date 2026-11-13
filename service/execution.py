"""Lightweight provider boundary and durable dispatch reconciliation.

No asyncio task owns a phase here. Repeated reconciliations use the same logical
operation and never transfer ownership based on time or an expired output.
"""
import os
import asyncio
import uuid


class ModalProvider:
    def __init__(self):
        import modal
        self.modal = modal
        self.function = modal.Function.from_name(os.environ['MODAL_APP_NAME'], os.environ.get('MODAL_FUNCTION_NAME','run_phase'))

    async def spawn(self, operation_id):
        async with asyncio.timeout(12):
            call = await self.function.spawn.aio(operation_id)
        return call.object_id

    async def poll(self, call_id):
        from modal.exception import OutputExpiredError, FunctionTimeoutError, TimeoutError
        call = self.modal.FunctionCall.from_id(call_id)
        try:
            await call.get.aio(timeout=0)
            return 'finished'
        except OutputExpiredError:
            return 'expired'
        except FunctionTimeoutError:
            return 'finished'
        except TimeoutError:
            return 'pending'
        # Other SDK/network errors provide no stop evidence. The worker wrapper
        # returns a small structured failure for ordinary bootstrap exceptions.

    async def cancel(self, call_id):
        call = self.modal.FunctionCall.from_id(call_id)
        async with asyncio.timeout(12):
            await call.cancel.aio(terminate_containers=True)
        # This is the provider's documented input+container termination ack.
        # Exceptions leave durable canceling, never a local fabricated stop.
        return True


async def reconcile(repo, provider, *, run_id=None, locked=False):
    """Bounded private queue; caller has already authorized a specific run."""
    for intent in repo.pending(limit=20, run_id=run_id):
        if locked:
            await _reconcile_one(repo, provider, intent)
        else:
            async with repo.control(intent['run_id']):
                # Work may have finished while obtaining the control lock.
                current = next((op for op in repo.pending(limit=100,run_id=intent['run_id']) if op['id'] == intent['id']),None)
                if current:
                    await _reconcile_one(repo, provider, current)


async def _reconcile_one(repo, provider, intent):
    submissions = repo.submissions(intent['id'])
    known = {s['provider_call_id'] for s in submissions if s['provider_call_id']}
    if intent['owner']:
        known.add(intent['owner'])
    if intent['cancel_intent']:
        try:
            for call in repo.provider_calls(intent['run_id']):
                if not await provider.cancel(call):
                    return
            # Unknown accepted inputs cannot claim the tombstoned operation.
            # Known owners and queued calls must have provider termination ack.
            if intent['owner']:
                repo.reconcile_stopped(intent['id'],intent['owner'],intent['fence'])
            from . import app as policy
            run = repo.get(intent['run_id'])
            if run['status'] == 'canceling':
                run['status'] = 'canceled'
                policy.emit(run,'done','Run canceled by visitor; available results retained.',{'status':'canceled','reason':'Canceled by visitor'})
        except Exception:
            return
        return
    if known:
        try:
            states = [await provider.poll(call) for call in known]
        except Exception:
            return
        if all(state in {'finished','stopped','expired'} for state in states):
            # A returned/expired provider output is never the saved result. Read
            # durable state again, and terminate before declaring interruption.
            run = repo.get(intent['run_id'])
            if run['status'] != 'running':
                return
            try:
                for call in known:
                    if not await provider.cancel(call):
                        return
            except Exception:
                return
            stopped = repo.reconcile_stopped(intent['id'],intent['owner'],intent['fence']) if intent['owner'] else repo.interrupt_unclaimed(intent['id'])
            if stopped:
                from . import app as policy
                run = repo.get(intent['run_id'])
                run['status'] = 'failed'
                policy.emit(run,'done','Remote execution stopped before completion; available results retained.',{'status':'failed','reason':'Remote execution interrupted.','code':'remote_execution_interrupted'})
        # Known submitted calls are never automatically resubmitted.
        return
    if intent['status'] != 'pending' or not repo.dispatch_due(intent['id']):
        return
    submission_id = str(uuid.uuid4())
    repo.register_submission(intent['id'], submission_id, ambiguous=True)
    try:
        call_id = await provider.spawn(intent['id'])
    except Exception:
        # Acceptance is unknown; retry only this same operation after backoff.
        return
    repo.register_submission(intent['id'], submission_id, call_id)
