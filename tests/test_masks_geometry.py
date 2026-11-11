"""Synthetic physical-coordinate fixtures; these are not measured cohort results."""
from pathlib import Path
import numpy as np
import pydicom
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from rt_utils import RTStructBuilder
from src.engine import EngineWorkspace
from test_engine import write_scan


def physical_tumor(root, patient_id='A', *, spacing=(2, 3), orientation=(1,0,0,0,1,0)):
    ct = write_scan(root, patient_id)
    # Deliberately rectangular pixels and image; filenames run opposite physical order.
    for path in ct.glob('*.dcm'):
        ds = pydicom.dcmread(path)
        ds.Columns = 10
        ds.PixelSpacing = list(spacing)
        ds.ImageOrientationPatient = list(orientation)
        ds.PixelData = np.full((8,10), -700, dtype=np.int16).tobytes()
        ds.save_as(path, enforce_file_format=True)
    rt = RTStructBuilder.create_new(dicom_series_path=str(ct))
    roi = np.zeros((10,8,4), dtype=bool)
    roi[2:5,1:4,1:4] = True
    rt.add_roi(mask=roi, name='GTV-1')
    # Independently specified DICOM patient coordinates: cols 1..3, rows 2..4.
    for i, contour in enumerate(rt.ds.ROIContourSequence[0].ContourSequence, start=1):
        contour.ContourData = [3,4,2*i, 9,4,2*i, 9,8,2*i, 3,8,2*i]
    rt.save(str(ct.parent / 'rtstruct.dcm'))
    return ct


def test_nonunit_physical_geometry_produces_correct_mask_volume_and_middle_overlay(tmp_path):
    physical_tumor(tmp_path / 'raw')
    with EngineWorkspace(tmp_path / 'raw', tmp_path / 'work') as engine:
        result = engine.run_stage('masks', ['A'])
        patient = result['patients'][0]
        assert patient['status'] == 'success', patient
        assert patient['values']['shape'] == [4,8,10]
        assert patient['values']['spacing_mm'] == [2,2,3]
        assert patient['values']['voxel_count'] == 27
        assert patient['values']['volume_cm3'] == .324
        assert patient['values']['slice_index'] == 2
        mask_artifact = next(a for a in patient['artifacts'] if a['role'] == 'mask')
        mask = np.load(engine.path / mask_artifact['path'])
        assert mask[2,2,1] == 1 and mask[2,4,3] == 1
        assert mask[2,1,2] == 0 and mask[0].sum() == 0
        overlay = next(a for a in patient['artifacts'] if a['role'] == 'overlay')
        assert (engine.path / overlay['path']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def test_misaligned_contour_fails_by_name_without_losing_other_patients(tmp_path):
    physical_tumor(tmp_path / 'raw', 'misaligned')
    physical_tumor(tmp_path / 'raw', 'good')
    path = tmp_path / 'raw' / 'misaligned' / 'rtstruct.dcm'
    ds = pydicom.dcmread(path)
    # It references the correct SOP UID, but lies 1 mm off its actual plane.
    contour = ds.ROIContourSequence[0].ContourSequence[0]
    contour.ContourData = [value + 1 if i % 3 == 2 else value for i, value in enumerate(contour.ContourData)]
    ds.save_as(path, enforce_file_format=True)
    with EngineWorkspace(tmp_path / 'raw', tmp_path / 'work') as engine:
        result = engine.run_stage('masks', ['misaligned','good'])
        assert result['status'] == 'partial'
        bad, good = result['patients']
        assert bad['patient_id'] == 'misaligned'
        assert bad['errors'][0]['code'] == 'mask_misaligned'
        assert bad['artifacts'] == []
        assert good['values']['volume_cm3'] == .324


def test_native_orientation_and_physical_slice_order_do_not_depend_on_filenames(tmp_path):
    ct = physical_tumor(tmp_path / 'raw')
    # A sagittal CT: column axis +Y, row axis +Z, slice normal +X.
    rotation = np.array([[0,0,1],[1,0,0],[0,1,0]])
    for path in ct.glob('*.dcm'):
        ds = pydicom.dcmread(path)
        ds.ImagePositionPatient = (rotation @ ds.ImagePositionPatient).tolist()
        ds.ImageOrientationPatient = [0,1,0,0,0,1]
        ds.save_as(path, enforce_file_format=True)
        path.rename(ct / f'reversed-{3-int(path.stem)}.dcm')
    rtpath = ct.parent / 'rtstruct.dcm'
    ds = pydicom.dcmread(rtpath)
    for contour in ds.ROIContourSequence[0].ContourSequence:
        coords = np.asarray(contour.ContourData).reshape(-1,3)
        contour.ContourData = (coords @ rotation.T).ravel().tolist()
    ds.save_as(rtpath, enforce_file_format=True)
    with EngineWorkspace(tmp_path / 'raw', tmp_path / 'work') as engine:
        first = engine.run_stage('masks', ['A'])['patients'][0]
        second = engine.run_stage('masks', ['A'])['patients'][0]
        assert first['status'] == 'success'
        assert first['values']['voxel_count'] == 27
        assert first['values']['slice_index'] == 2
        assert first['values']['geometry']['direction_lps'] == rotation.tolist()
        assert first['artifacts'][1]['sha256'] == second['artifacts'][1]['sha256']
        mask = np.load(engine.path / first['artifacts'][0]['path'])
        assert mask[0].sum() == 0 and mask[3].sum() == 9


def test_missing_spacing_is_named_failure_instead_of_unit_spacing(tmp_path):
    ct = physical_tumor(tmp_path / 'raw')
    ds = pydicom.dcmread(ct / '0.dcm')
    del ds.PixelSpacing
    ds.save_as(ct / '0.dcm', enforce_file_format=True)
    with EngineWorkspace(tmp_path / 'raw', tmp_path / 'work') as engine:
        for stage in ['masks','features']:
            patient = engine.run_stage(stage, ['A'])['patients'][0]
            assert patient['status'] == 'failed'
            assert patient['errors'][0]['code'] == 'unsupported_geometry'
            assert not patient['artifacts']


def test_empty_tumor_and_absent_roi_are_distinct_named_failures(tmp_path):
    ct = physical_tumor(tmp_path / 'raw')
    rtpath = ct.parent / 'rtstruct.dcm'
    ds = pydicom.dcmread(rtpath)
    ds.ROIContourSequence[0].ContourSequence = Sequence([])
    ds.save_as(rtpath, enforce_file_format=True)
    with EngineWorkspace(tmp_path / 'raw', tmp_path / 'work') as engine:
        empty = engine.run_stage('masks', ['A'])['patients'][0]
        absent = engine.run_stage('masks', ['A'], roi_name='absent')['patients'][0]
        assert empty['errors'][0]['code'] == 'empty_mask'
        assert absent['errors'][0]['code'] == 'missing_roi'


def test_features_use_verified_physical_spacing_for_shape_measurements(tmp_path):
    ct = physical_tumor(tmp_path / 'raw')
    for path in ct.glob('*.dcm'):
        ds = pydicom.dcmread(path)
        ds.PixelData = (np.arange(80,dtype=np.int16).reshape(8,10) + int(path.stem)).tobytes()
        ds.save_as(path,enforce_file_format=True)
    with EngineWorkspace(tmp_path / 'raw', tmp_path / 'work') as engine:
        patient = engine.run_stage('features', ['A'])['patients'][0]
        assert patient['status'] == 'success', patient
        # Resampling preserves this rectangular 6 × 6 × 9 mm voxel support.
        assert patient['values']['original_shape_VoxelVolume'] == 324


def test_roi_without_contour_sequence_has_named_empty_mask_failure(tmp_path):
    ct = physical_tumor(tmp_path / 'raw')
    rtpath = ct.parent / 'rtstruct.dcm'
    ds = pydicom.dcmread(rtpath)
    del ds.ROIContourSequence[0].ContourSequence
    ds.save_as(rtpath, enforce_file_format=True)
    with EngineWorkspace(tmp_path / 'raw', tmp_path / 'work') as engine:
        patient = engine.run_stage('masks', ['A'])['patients'][0]
        assert patient['errors'][0]['code'] == 'empty_mask'
