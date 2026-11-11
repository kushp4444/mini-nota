"""Explicit development fixture catalog, replaced by the frozen held-out manifest later."""
from service.catalog import DATABASE_URL
import psycopg
with psycopg.connect(DATABASE_URL) as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS patient_catalog (patient_id text PRIMARY KEY, label text NOT NULL, fixture boolean NOT NULL)')
    for i in range(1, 4):
        conn.execute('INSERT INTO patient_catalog VALUES (%s,%s,true) ON CONFLICT (patient_id) DO NOTHING',
                     (f'LUNG1-{i:03}', 'Public Lung1 · development fixture'))
