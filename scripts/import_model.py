"""Import immutable model metadata into the read-only catalog, never visitor results."""
import argparse
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from src.frozen_model import FrozenModel
from service.catalog import DATABASE_URL


def import_model(path, *, database_url=DATABASE_URL):
    model = FrozenModel(path)
    metadata = model.metadata()
    with psycopg.connect(database_url) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS model_metadata (singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), metadata jsonb NOT NULL)')
        conn.execute('LOCK TABLE model_metadata IN ACCESS EXCLUSIVE MODE')
        # A real frozen catalog must agree with the trained partition exactly.
        frozen = conn.execute("SELECT to_regclass('catalog_metadata')").fetchone()[0]
        if frozen:
            catalog = conn.execute('SELECT partition_sha256 FROM catalog_metadata WHERE singleton').fetchone()
            if catalog and catalog[0] != metadata['partition_sha256']:
                raise ValueError('Model partition differs from frozen catalog')
        actual = [r[0] for r in conn.execute('SELECT patient_id FROM patient_catalog ORDER BY patient_id')]
        if actual != sorted(model.bundle['partition']['held_out']):
            raise ValueError('Catalog membership differs from model held-out partition')
        existing = conn.execute('SELECT metadata FROM model_metadata WHERE singleton').fetchone()
        if existing and existing[0]['model_version'] != model.version:
            raise ValueError('Model already frozen; provision a separately versioned catalog for replacement')
        conn.execute('INSERT INTO model_metadata VALUES(true,%s) ON CONFLICT(singleton) DO NOTHING',(Jsonb(metadata),))
    return metadata


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',required=True,type=Path)
    print(import_model(parser.parse_args().bundle))

if __name__ == '__main__': main()
