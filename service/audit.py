"""Ordered audit event identity shared by dispatcher and durable writes."""
from datetime import datetime, timezone


def last_sequence(run):
    return run.get('sequence_base', 0) + len(run['events'])


def append_event(run, kind, message, payload=None):
    sequence = last_sequence(run) + 1
    run['events'].append({
        'id': f"{run['id']}:{sequence}",
        'run_id': run['id'],
        'sequence': sequence,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'kind': kind,
        'message': message,
        'payload': payload or {},
    })
