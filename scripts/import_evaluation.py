"""Import an immutable full held-out evaluation, separately from the frozen bundle."""
import argparse
import json
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from service.catalog import DATABASE_URL
from src.frozen_model import FrozenModel, digest


def import_evaluation(bundle, asset, *, database_url=DATABASE_URL):
    model=FrozenModel(bundle);evaluation=json.loads(Path(asset).read_text())
    content={k:v for k,v in evaluation.items() if k!='evaluation_version'}
    if evaluation['evaluation_version']!='held-out-v1-'+digest(content)[:20]:raise ValueError('Evaluation checksum mismatch')
    if evaluation['bundle_sha256']!=model.bundle['bundle_sha256'] or evaluation['model_version']!=model.version:
        raise ValueError('Evaluation does not match frozen model')
    with psycopg.connect(database_url) as conn:
        metadata=conn.execute('SELECT metadata FROM model_metadata WHERE singleton').fetchone()
        if not metadata or metadata[0]['model_version']!=model.version:raise ValueError('Catalog model mismatch')
        conn.execute('CREATE TABLE IF NOT EXISTS model_evaluation (model_version text PRIMARY KEY, evaluation jsonb NOT NULL)')
        conn.execute('LOCK TABLE model_evaluation IN ACCESS EXCLUSIVE MODE')
        existing=conn.execute('SELECT evaluation FROM model_evaluation WHERE model_version=%s',(model.version,)).fetchone()
        if existing and existing[0]!=evaluation:raise ValueError('Evaluation already frozen; use separately versioned deployment')
        conn.execute('INSERT INTO model_evaluation VALUES(%s,%s) ON CONFLICT DO NOTHING',(model.version,Jsonb(evaluation)))
    return evaluation['evaluation_version']


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',required=True);p.add_argument('--evaluation',required=True)
    a=p.parse_args();print(import_evaluation(a.bundle,a.evaluation))
if __name__=='__main__':main()
