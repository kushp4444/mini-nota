"""Atomically import a frozen held-out catalog, or explicitly seed development fixtures.

python -m scripts.seed_catalog --prepared data/processed/library-v1
Fixture seeding must use --fixtures and refuses a database with a frozen catalog.
"""
import argparse
import hashlib
import json
from pathlib import Path
import psycopg
from service.catalog import DATABASE_URL


def _create_tables(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS patient_catalog (patient_id text PRIMARY KEY, label text NOT NULL, fixture boolean NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS catalog_metadata (singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), partition_sha256 text NOT NULL, preparation_path text NOT NULL, development_count integer NOT NULL, held_out_count integer NOT NULL)')


def import_prepared_catalog(prepared_dir, *, database_url=DATABASE_URL):
    """Only exact disjoint, checksummed held-out membership can enter the live catalog."""
    directory = Path(prepared_dir).resolve()
    raw = (directory / 'partition.json').read_bytes()
    partition = json.loads(raw)
    catalog = json.loads((directory / 'catalog.json').read_text())
    development, held_out = partition['development'], partition['held_out']
    rows = catalog['patients']
    if (not held_out or len(set(held_out)) != len(held_out)
            or len(set(development)) != len(development)
            or set(development) & set(held_out)
            or sorted(p['id'] for p in rows) != sorted(held_out)
            or any(p['fixture'] is not False for p in rows)
            or catalog['partition_sha256'] != hashlib.sha256(raw).hexdigest()):
        raise ValueError('Frozen catalog does not match disjoint held-out partition')
    with psycopg.connect(database_url) as conn:
        _create_tables(conn)
        conn.execute('LOCK TABLE patient_catalog IN ACCESS EXCLUSIVE MODE')
        existing = conn.execute('SELECT partition_sha256 FROM catalog_metadata WHERE singleton').fetchone()
        if existing and existing[0] != catalog['partition_sha256']:
            raise ValueError('Catalog is already frozen to a different partition; provision a separately versioned database')
        conn.execute('DELETE FROM patient_catalog')
        for row in sorted(rows, key=lambda p: p['id']):
            conn.execute('INSERT INTO patient_catalog VALUES (%s,%s,false)', (row['id'], row['label']))
        conn.execute('INSERT INTO catalog_metadata VALUES (true,%s,%s,%s,%s) ON CONFLICT(singleton) DO UPDATE SET partition_sha256=EXCLUDED.partition_sha256, preparation_path=EXCLUDED.preparation_path, development_count=EXCLUDED.development_count, held_out_count=EXCLUDED.held_out_count',
            (catalog['partition_sha256'], str(directory), len(development), len(held_out)))
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--prepared', type=Path)
    source.add_argument('--fixtures', action='store_true')
    args = parser.parse_args()
    if args.prepared:
        print(f'Imported {import_prepared_catalog(args.prepared)} real frozen held-out patients')
    else:
        with psycopg.connect(DATABASE_URL) as conn:
            _create_tables(conn)
            if conn.execute('SELECT count(*) FROM catalog_metadata').fetchone()[0]:
                raise ValueError('Refusing fixture seed over a frozen catalog; use an isolated test database')
            for i in range(1, 4):
                conn.execute('INSERT INTO patient_catalog VALUES (%s,%s,true) ON CONFLICT (patient_id) DO NOTHING',
                    (f'LUNG1-{i:03}', 'Public Lung1 · development fixture'))


if __name__ == '__main__':
    main()
