"""Public offline preparation behavior; generated data is synthetic."""
import json
import pytest
from src.preparation import freeze_partition


def test_partition_is_reproducible_disjoint_and_balances_events(tmp_path):
    rows = [{'patient_id': f'LUNG1-{i:03}', 'scoring_eligible': True,
             'outcome': {'duration': 100 + i, 'event': i % 2}} for i in range(1, 21)]
    rows.append({'patient_id': 'LUNG1-021', 'scoring_eligible': False, 'outcome': None})
    first = freeze_partition(rows, seed=42)
    assert first == freeze_partition(list(reversed(rows)), seed=42)
    assert len(first['development']) == 16 and len(first['held_out']) == 4
    assert set(first['development']).isdisjoint(first['held_out'])
    assert set(first['development'] + first['held_out']) == {r['patient_id'] for r in rows[:20]}
    assert sum(int(p.rsplit('-', 1)[1]) % 2 for p in first['held_out']) == 2
    with pytest.raises(ValueError, match='Duplicate'):
        freeze_partition(rows + [rows[0]])


def test_preparation_accounts_for_processing_and_outcome_failures(tmp_path):
    import csv
    import pydicom
    from test_masks_geometry import physical_tumor
    from src.preparation import prepare_collection
    manifest = []
    for patient_id in ('LUNG1-001', 'LUNG1-002'):
        ct = physical_tumor(tmp_path / 'source', patient_id)
        for path in ct.glob('*.dcm'):
            ds = pydicom.dcmread(path)
            ds.PatientID = ds.PatientName = patient_id
            # Nonconstant signal is required for configured normalization.
            import numpy as np
            ds.PixelData = np.arange(80, dtype=np.int16).reshape(8, 10).tobytes()
            ds.save_as(path, enforce_file_format=True)
        rtpath = ct.parent / 'rtstruct.dcm'
        ds = pydicom.dcmread(rtpath)
        ds.PatientID = patient_id
        if patient_id.endswith('002'):
            ds.StructureSetROISequence[0].ROIName = 'NOT-TUMOR'
        ds.save_as(rtpath, enforce_file_format=True)
        for modality, path, files in [('CT', ct, list(ct.glob('*.dcm'))), ('RTSTRUCT', rtpath.parent, [rtpath])]:
            header = pydicom.dcmread(files[0], stop_before_pixels=True)
            manifest.append({'patient_id': patient_id, 'modality': modality,
                'series_uid': str(header.SeriesInstanceUID), 'expected_instances': len(files),
                'files': [str(p) for p in files]})
    clinical = tmp_path / 'clinical.csv'
    clinical.write_text('patient_id,survivaltime,deadstatusevent\nLUNG1-001,,1\nLUNG1-002,100,2\n')
    result = prepare_collection(manifest, clinical, tmp_path / 'prepared', workers=1)
    assert result['counts'] == {'inventoried': 2, 'scoring_eligible': 1, 'processing_excluded': 1,
                                'evaluation_eligible': 0, 'evaluation_excluded': 1,
                                'development': 1, 'held_out': 0}
    records = result['patients']
    assert records[0]['scoring_eligible'] is True and records[0]['outcome'] is None
    assert records[0]['evaluation_exclusions'][0]['code'] == 'invalid_duration'
    assert records[1]['processing_exclusions'][0]['code'] == 'missing_roi'
    assert len(records[0]['stages']['features']['feature_schema']) == 72
    assert (tmp_path / 'prepared/features.csv').is_file()
    assert json.loads((tmp_path / 'prepared/partition.json').read_text())['development'] == ['LUNG1-001']
    assert prepare_collection(manifest, clinical, tmp_path / 'prepared', workers=1) == result


def test_incomplete_acquisition_is_not_reported_as_patient_exclusion(tmp_path):
    from src.preparation import prepare_collection
    with pytest.raises(ValueError, match='Acquisition incomplete'):
        prepare_collection([{'patient_id': 'LUNG1-001', 'modality': 'CT',
            'series_uid': '1.2.3', 'expected_instances': 2, 'files': []}],
            tmp_path / 'clinical.csv', tmp_path / 'output')
    assert not (tmp_path / 'output/report.json').exists()
