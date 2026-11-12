"""Frozen catalog import and public API selection use an isolated PostgreSQL schema."""
import json
import hashlib
import uuid
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from fastapi.testclient import TestClient
from service import catalog
from service.app import app


def test_frozen_catalog_is_idempotent_and_server_rejects_development(tmp_path, monkeypatch):
    from scripts.seed_catalog import import_prepared_catalog
    schema = 'test_catalog_' + uuid.uuid4().hex
    url = catalog.DATABASE_URL
    isolated = make_conninfo(url, options=f'-c search_path={schema}')
    with psycopg.connect(url) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:
        partition = {'development': ['LUNG1-001'], 'held_out': ['LUNG1-002']}
        (tmp_path / 'partition.json').write_text(json.dumps(partition))
        (tmp_path / 'catalog.json').write_text(json.dumps({'partition_sha256': hashlib.sha256((tmp_path / 'partition.json').read_bytes()).hexdigest(),
            'patients': [{'id': 'LUNG1-002', 'fixture': False, 'label': 'Public Lung1 · frozen held-out patient'}]}))
        import_prepared_catalog(tmp_path, database_url=isolated)
        monkeypatch.setattr(catalog, 'DATABASE_URL', isolated)
        assert catalog.patients() == [{'id': 'LUNG1-002', 'label': 'Public Lung1 · frozen held-out patient', 'fixture': False}]
        import_prepared_catalog(tmp_path, database_url=isolated)
        assert len(catalog.patients()) == 1
        with TestClient(app) as client:
            assert client.post('/runs', json={'patient_ids': ['LUNG1-001']}).status_code == 422
            assert client.post('/runs', json={'patient_ids': ['LUNG1-001', 'LUNG1-002']}).status_code == 422
        # Corrupt membership cannot replace a previously valid frozen catalog.
        partition['held_out'].append('LUNG1-001')
        (tmp_path / 'partition.json').write_text(json.dumps(partition))
        import pytest
        with pytest.raises(ValueError):
            import_prepared_catalog(tmp_path, database_url=isolated)
        assert [p['id'] for p in catalog.patients()] == ['LUNG1-002']
    finally:
        with psycopg.connect(url) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
