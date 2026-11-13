"""Durable run and worker ownership boundary; no imaging/native dependencies.

All writes lock the run row. Worker publications additionally require an exact
operation/owner/fence, current revision and absent durable cancellation intent.
Time alone never transfers an operation. See docs/ticket-16-handoff.md.
"""
import asyncio
import hashlib
import hmac
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from .audit import append_event

TERMINAL = {'completed', 'failed', 'canceled'}
DISPATCH_ATTEMPTS = 3
DISPATCH_BACKOFF_SECONDS = 30


class Conflict(Exception):
    pass


class RunRepository:
    def __init__(self, database_url):
        self.database_url = database_url

    def initialize(self):
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            for migration in sorted(Path(__file__).parents[1].joinpath('migrations').glob('*.sql')):
                conn.execute(migration.read_text())

    def get(self, run_id):
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            row = conn.execute('SELECT document, revision, secret_digest FROM visitor_runs WHERE id=%s', (run_id,)).fetchone()
        if not row:
            return None
        return {**row[0], '_revision':row[1], '_secret_digest':row[2]}

    def authorize(self, run_id, secret):
        run = self.get(run_id)
        if run and not hmac.compare_digest(run.pop('_secret_digest'), hashlib.sha256(secret.encode()).hexdigest()):
            raise PermissionError('Run access denied')
        if run:
            run['secret'] = secret
        return run

    def create(self, run, nonce=None, phase='imaging'):
        """Atomic launch receipt and dispatch intent. Returns (snapshot, created)."""
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            inserted = conn.execute('INSERT INTO visitor_runs(id,launch_nonce,secret_digest,document) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id',
                         (run['id'], nonce, hashlib.sha256(run['secret'].encode()).hexdigest(), Jsonb(self.document(run)))).fetchone()
            row = conn.execute('SELECT id, document, revision,secret_digest FROM visitor_runs WHERE id=%s FOR UPDATE', (run['id'],)).fetchone()
            if row is None or row[1]['patient_ids'] != run['patient_ids'] or not hmac.compare_digest(row[3],hashlib.sha256(run['secret'].encode()).hexdigest()):
                raise Conflict('Launch identity was already used for a different selection or capability')
            created = bool(inserted)
            if created:
                if phase:
                    self._operation(conn,run['id'],phase,0)
                conn.execute('UPDATE visitor_runs SET revision=1 WHERE id=%s', (run['id'],))
            return {**row[1], 'secret':run['secret'], '_revision':1 if created else row[2]}, created

    @staticmethod
    def document(run):
        def reject(value):
            if isinstance(value, dict):
                if 'data_base64' in value:
                    raise ValueError('Binary artifacts must be externalized before persistence')
                return {k:reject(v) for k,v in value.items()}
            if isinstance(value, list):
                return [reject(v) for v in value]
            return value
        return reject({k:v for k,v in run.items() if not k.startswith('_') and k not in {'secret','task','control_lock','touched'}})

    def _operation(self, conn, run_id, phase, generation):
        operation_id = hashlib.sha256(f'{run_id}:{phase}:{generation}'.encode()).hexdigest()
        inserted = conn.execute('INSERT INTO execution_operations(id,run_id,phase,generation) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id',
                                (operation_id,run_id,phase,generation)).fetchone()
        return {'id':operation_id,'new':bool(inserted)}

    def operation(self, run_id, phase='imaging', generation=0):
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            row = conn.execute('SELECT id,status,owner,fence,submission_state,attempt_id FROM execution_operations WHERE run_id=%s AND phase=%s AND generation=%s', (run_id,phase,generation)).fetchone()
        return dict(zip(('id','status','owner','fence','submission_state','attempt_id'),row)) if row else None

    def operation_context(self, operation_id):
        """Private worker bootstrap; snapshot contains a digest, no capability."""
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            row = conn.execute('SELECT run_id,phase,generation FROM execution_operations WHERE id=%s',(operation_id,)).fetchone()
        if not row:
            return None
        return {'run':self.get(row[0]),'phase':row[1],'generation':row[2]}

    def register_submission(self, operation_id, submission_id, provider_call_id=None, ambiguous=False):
        """Record every dispatch attempt, including unknown provider acceptance.

        This never claims compute ownership or clears an existing owner.
        """
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            conn.execute(
                """SELECT r.id FROM visitor_runs r JOIN execution_operations o ON o.run_id=r.id
                   WHERE o.id=%s FOR UPDATE OF r""",
                (operation_id,),
            )
            conn.execute('INSERT INTO operation_submissions(operation_id,submission_id,provider_call_id,ambiguous) VALUES (%s,%s,%s,%s) ON CONFLICT (operation_id,submission_id) DO UPDATE SET provider_call_id=COALESCE(EXCLUDED.provider_call_id,operation_submissions.provider_call_id),ambiguous=EXCLUDED.ambiguous',
                         (operation_id,submission_id,provider_call_id,ambiguous))
            conn.execute("UPDATE execution_operations SET submission_state=%s WHERE id=%s AND status='pending'", ('ambiguous' if ambiguous else 'submitted',operation_id))

    def submissions(self, operation_id):
        """Private provider-reconciliation registrations, including ambiguity."""
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            rows = conn.execute('SELECT submission_id,provider_call_id,ambiguous FROM operation_submissions WHERE operation_id=%s ORDER BY created_at,submission_id',(operation_id,)).fetchall()
            return [dict(zip(('submission_id','provider_call_id','ambiguous'),row)) for row in rows]

    def claim(self, operation_id, owner, *, attempt_id=None):
        """Worker self-registration, BEFORE loading scans/importing native code.

        Returns fence token or None. Duplicate invocation/claim never computes.
        """
        attempt_id = attempt_id or str(uuid.uuid4())
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            op = conn.execute('SELECT run_id,phase,generation FROM execution_operations WHERE id=%s', (operation_id,)).fetchone()
            if not op:
                return None
            run = conn.execute('SELECT document,cancel_intent FROM visitor_runs WHERE id=%s FOR UPDATE',(op[0],)).fetchone()
            if run[1] or run[0]['status'] != 'running' or (op[1] == 'scoring' and (op[2] != run[0].get('gate_generation') or run[0].get('approved_disclosure') != (run[0].get('checkpoint') or {}).get('disclosure_id'))):
                return None
            row = conn.execute("UPDATE execution_operations SET owner=%s,attempt_id=%s,fence=fence+1,status='owned' WHERE id=%s AND status='pending' AND owner IS NULL RETURNING fence", (owner,attempt_id,operation_id)).fetchone()
            return row[0] if row else None

    def owns(self, operation):
        """Current exact ownership; cancellation and terminal state fail closed."""
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            row = conn.execute("SELECT 1 FROM execution_operations o JOIN visitor_runs r ON r.id=o.run_id WHERE o.id=%s AND o.owner=%s AND o.fence=%s AND (%s::text IS NULL OR o.attempt_id=%s) AND o.status='owned' AND NOT r.cancel_intent AND r.document->>'status'='running'", (operation['id'],operation['owner'],operation['fence'],operation.get('attempt_id'),operation.get('attempt_id'))).fetchone()
            return bool(row)

    def publish(self, run, operation=None, cancel=False, approve=False):
        """Atomic snapshot/results + ordered audit + operation transition.

        Stale writers fail closed, including canceled or superseded workers.
        Approval creates one scoring intent in the SAME transaction as audit.
        """
        document = self.document(run)
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            old = conn.execute('SELECT document,revision,cancel_intent FROM visitor_runs WHERE id=%s FOR UPDATE',(run['id'],)).fetchone()
            if old is None or old[1] != run['_revision']:
                raise Conflict('Run changed; reload before publishing')
            if operation:
                row = conn.execute('SELECT status,owner,fence,attempt_id FROM execution_operations WHERE id=%s AND run_id=%s FOR UPDATE',(operation['id'],run['id'])).fetchone()
                if not row or row[:3] != ('owned',operation['owner'],operation['fence']) or (operation.get('attempt_id') and row[3] != operation['attempt_id']) or old[2]:
                    raise Conflict('Worker lost ownership or run was canceled')
            if old[0]['status'] in TERMINAL and document != old[0] and not (operation and document['status'] == old[0]['status']):
                raise Conflict('Terminal run is immutable')
            if old[2] and run['status'] not in {'canceling','canceled'}:
                raise Conflict('Cancellation blocks advancement')
            if document['patient_ids'] != old[0]['patient_ids'] or document.get('model') != old[0].get('model'):
                raise Conflict('Selected cohort and pinned model context are immutable')
            for results in document.get('stage_results',{}).values():
                identities = [patient['patient_id'] for patient in results]
                if len(identities) != len(set(identities)) or not set(identities) <= set(document['patient_ids']):
                    raise Conflict('Stage results must account for distinct selected patients')
            self._save_snapshot(conn, document, old[0].get('events', []), cancel=cancel)
            if approve:
                self._operation(conn,run['id'],'scoring',run['gate_generation'])
            if operation and document.get('events') and document['events'][-1]['kind'] in {'done','gate'}:
                conn.execute("UPDATE execution_operations SET status='finished' WHERE id=%s", (operation['id'],))
            if run['status'] == 'canceled':
                conn.execute("UPDATE execution_operations SET status='stopped' WHERE run_id=%s AND status IN ('pending','owned')",(run['id'],))
        run['_revision'] += 1

    @staticmethod
    def _save_snapshot(conn, document, old_events, *, cancel=False):
        run_id = document['id']
        events = document.get('events', [])
        if events[:len(old_events)] != old_events:
            raise Conflict('Audit history cannot be rewritten')
        for offset, event in enumerate(events[len(old_events):], 1):
            expected = document.get('sequence_base', 0) + len(old_events) + offset
            if event.get('sequence') != expected or event.get('run_id') != run_id or event.get('id') != f'{run_id}:{expected}':
                raise Conflict('Audit events must be consecutive and run-owned')
            conn.execute('INSERT INTO run_events(run_id,sequence,event) VALUES (%s,%s,%s)',
                         (run_id, expected, Jsonb(event)))
        conn.execute('UPDATE visitor_runs SET document=%s,revision=revision+1,cancel_intent=cancel_intent OR %s WHERE id=%s',
                     (Jsonb(document), cancel, run_id))

    def interrupt(self, intent, *, unconfirmed_dispatch=False):
        """Fence an interrupted operation and append its terminal audit atomically."""
        run_id = intent['run_id']
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            old = conn.execute(
                'SELECT document, cancel_intent FROM visitor_runs WHERE id=%s FOR UPDATE',
                (run_id,),
            ).fetchone()
            if old is None or old[1] or old[0]['status'] != 'running':
                return
            if unconfirmed_dispatch:
                attempts, backed_off, accepted = self._dispatch_attempts(conn, intent['id'])
                if accepted or attempts < DISPATCH_ATTEMPTS or not backed_off:
                    return
                row = conn.execute(
                    """UPDATE execution_operations SET status='interrupted', fence=fence+1
                       WHERE id=%s AND run_id=%s AND status='pending'
                       AND owner IS NULL AND fence=%s RETURNING id""",
                    (intent['id'], run_id, intent['fence']),
                ).fetchone()
                reason = 'Remote execution could not be confirmed after repeated dispatch attempts.'
                message = 'Remote dispatch could not be confirmed; available results retained.'
                code = 'remote_dispatch_unconfirmed'
            else:
                row = conn.execute(
                    """UPDATE execution_operations SET status='interrupted'
                       WHERE id=%s AND run_id=%s AND status IN (%s, 'interrupted')
                       AND owner IS NOT DISTINCT FROM %s AND fence=%s RETURNING id""",
                    (intent['id'], run_id, 'owned' if intent['owner'] else 'pending',
                     intent['owner'], intent['fence']),
                ).fetchone()
                reason = 'Remote execution interrupted.'
                message = 'Remote execution stopped before completion; available results retained.'
                code = 'remote_execution_interrupted'
            if row is None:
                return
            document = old[0]
            old_events = document['events'][:]
            document['status'] = 'failed'
            append_event(document, 'done', message, {'status': 'failed', 'reason': reason, 'code': code})
            self._save_snapshot(conn, document, old_events)

    def reconcile_stopped(self, operation_id, owner, fence):
        """Record an owned invocation stop during cancellation, after provider acknowledgement.

        Canceling runs remain discoverable until the terminal audit is saved.
        """
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            row = conn.execute(
                """UPDATE execution_operations o SET status='interrupted'
                   FROM visitor_runs r WHERE r.id=o.run_id AND r.cancel_intent
                   AND o.id=%s AND o.owner=%s AND o.fence=%s AND o.status='owned' RETURNING o.id""",
                (operation_id, owner, fence),
            ).fetchone()
            return bool(row)

    def provider_calls(self, run_id):
        """All known accepted/owned calls, including the gate-return tail."""
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            rows = conn.execute("SELECT owner FROM execution_operations WHERE run_id=%s AND owner IS NOT NULL UNION SELECT s.provider_call_id FROM operation_submissions s JOIN execution_operations o ON o.id=s.operation_id WHERE o.run_id=%s AND s.provider_call_id IS NOT NULL",(run_id,run_id)).fetchall()
            return {row[0] for row in rows}

    def active_owners(self, run_id):
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            rows = conn.execute("SELECT id,owner,fence FROM execution_operations WHERE run_id=%s AND status='owned'",(run_id,)).fetchall()
            return [dict(zip(('id','owner','fence'),row)) for row in rows]

    @staticmethod
    def _dispatch_attempts(conn, operation_id):
        return conn.execute(
            """SELECT count(*), max(created_at) < now() - make_interval(secs => %s),
                      bool_or(provider_call_id IS NOT NULL)
               FROM operation_submissions WHERE operation_id=%s""",
            (DISPATCH_BACKOFF_SECONDS, operation_id),
        ).fetchone()

    def dispatch_due(self, operation_id):
        # Give unknown calls time to claim, including after the final attempt.
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            attempts, backed_off, _ = self._dispatch_attempts(conn, operation_id)
            return attempts == 0 or (attempts < DISPATCH_ATTEMPTS and bool(backed_off))

    def pending(self, limit=20, run_id=None):
        """Private dispatcher reconciliation input, NEVER a public run listing."""
        with psycopg.connect(self.database_url, connect_timeout=10) as conn:
            rows = conn.execute(
                """SELECT o.id,o.run_id,o.status,o.owner,o.fence,o.submission_state,r.cancel_intent
                   FROM execution_operations o JOIN visitor_runs r ON r.id=o.run_id
                   WHERE (o.status IN ('pending','owned')
                       OR (o.status='interrupted' AND r.document->>'status'='running')
                       OR (r.cancel_intent AND r.document->>'status'='canceling'))
                   AND (%s::text IS NULL OR o.run_id=%s) ORDER BY o.created_at LIMIT %s""",
                (run_id, run_id, min(limit, 100)),
            ).fetchall()
            return [dict(zip(('id','run_id','status','owner','fence','submission_state','cancel_intent'),r)) for r in rows]

    @asynccontextmanager
    async def control(self, run_id):
        # Transaction-scoped advisory locks also work through transaction poolers.
        conn = psycopg.connect(self.database_url,autocommit=False,connect_timeout=10)
        try:
            while not conn.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))',(run_id,)).fetchone()[0]:
                await asyncio.sleep(.02)
            yield
        finally:
            conn.close()
