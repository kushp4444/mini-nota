"""Immutable catalog only: no visitor rows are ever written here."""
import os
import psycopg

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://mini_nota@127.0.0.1:55432/mini_nota')

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
        return row[0] if row else None
