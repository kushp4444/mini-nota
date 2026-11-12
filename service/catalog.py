"""Immutable catalog only: no visitor rows are ever written here."""
import os
import psycopg

DATABASE_URL = os.environ.get('CATALOG_DATABASE_URL') or os.environ.get('DATABASE_URL', 'postgresql://mini_nota@127.0.0.1:55432/mini_nota')

def patients():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT patient_id, label, fixture FROM patient_catalog ORDER BY patient_id')
            return [{'id': r[0], 'label': r[1], 'fixture': r[2]} for r in cur.fetchall()]


def model_metadata():
    with psycopg.connect(DATABASE_URL) as conn:
        try:
            row = conn.execute('SELECT metadata FROM model_metadata WHERE singleton').fetchone()
        except psycopg.errors.UndefinedTable:
            return None
        if not row:return None
        metadata = row[0]
        if conn.execute("SELECT to_regclass('model_evaluation')").fetchone()[0]:
            evaluation = conn.execute('SELECT evaluation FROM model_evaluation WHERE model_version=%s',(metadata['model_version'],)).fetchone()
            if evaluation:metadata['evaluation']=evaluation[0]
        return metadata
