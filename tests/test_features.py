"""Feature contracts use synthetic physical fixtures, never cohort measurements."""
import csv
import io
import json
import math
import numpy as np
import pydicom
import pytest
from src.engine import EngineWorkspace
from src.extract_features import extract_one
from test_masks_geometry import physical_tumor


def varied_tumor(root, patient_id='A'):
    ct = physical_tumor(root, patient_id)
    for path in ct.glob('*.dcm'):
        ds = pydicom.dcmread(path)
        ds.PixelData = (np.arange(80, dtype=np.int16).reshape(8,10) + int(path.stem)).tobytes()
        ds.save_as(path, enforce_file_format=True)
    return ct


def test_offline_stage_returns_ordered_numeric_rows_and_portable_csv(tmp_path):
    varied_tumor(tmp_path / 'raw')
    with EngineWorkspace(tmp_path / 'raw', tmp_path / 'work') as engine:
        result = engine.run_stage('features', ['A'])
        patient = result['patients'][0]
        assert patient['status'] == 'success', patient
        schema = patient['feature_schema']
        assert len(schema) == 72 and schema == sorted(schema)
        assert list(patient['values']) == schema
        assert all(type(v) is float and math.isfinite(v) for v in patient['values'].values())
        # Independently authored 6 × 6 × 9 mm support (same fixture as mask test).
        assert patient['values']['original_shape_VoxelVolume'] == pytest.approx(324, abs=1e-6)
        artifact = next(a for a in patient['artifacts'] if a['media_type'] == 'text/csv')
        rows = list(csv.DictReader(io.StringIO((engine.path / artifact['path']).read_text())))
        assert rows[0]['patient_id'] == 'A'
        assert float(rows[0]['original_shape_VoxelVolume']) == pytest.approx(324, abs=1e-6)
        assert list(rows[0]) == ['patient_id', *schema]
        json.dumps(result, allow_nan=False)


def test_nonfinite_input_has_explicit_disposition_and_no_silent_fill():
    image = np.arange(64, dtype=float).reshape(4,4,4)
    image[1,1,1] = np.nan
    mask = np.zeros_like(image, dtype=bool)
    mask[1:3,1:3,1:3] = True
    with pytest.raises(ValueError, match='Non-finite image values'):
        extract_one(image, mask, (1,1,1))


def test_constant_normalized_image_fails_by_name_and_other_patients_continue(tmp_path):
    physical_tumor(tmp_path / 'raw', 'constant')
    varied_tumor(tmp_path / 'raw', 'good')
    with EngineWorkspace(tmp_path / 'raw', tmp_path / 'work') as engine:
        result = engine.run_stage('features', ['constant', 'good'])
        bad, good = result['patients']
        assert result['status'] == 'partial'
        assert bad['patient_id'] == 'constant'
        assert bad['errors'][0]['code'] == 'invalid_feature_input'
        assert 'zero variance' in bad['errors'][0]['message']
        assert bad['values'] == {} and bad['artifacts'] == []
        assert good['status'] == 'success'
