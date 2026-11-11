"""Behavior checks at the selected-patient stage boundary, using real DICOM."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

from rt_utils import RTStructBuilder

from src.engine import EngineWorkspace


def write_scan(root, patient_id):
    ct = root / patient_id / 'ct'
    ct.mkdir(parents=True)
    study, series, frame = generate_uid(), generate_uid(), generate_uid()
    for z in range(4):
        file_meta = FileMetaDataset()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        file_meta.MediaStorageSOPClassUID = CTImageStorage
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds = FileDataset(str(ct / f'{z}.dcm'), {}, file_meta=file_meta, preamble=b'\0' * 128)
        ds.SOPClassUID = CTImageStorage
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        ds.StudyInstanceUID, ds.SeriesInstanceUID = study, series
        ds.FrameOfReferenceUID = frame
        ds.Modality, ds.PatientID = 'CT', 'header-id-is-not-selection'
        ds.PatientName, ds.PatientBirthDate = '', ''
        ds.StudyDate, ds.StudyTime, ds.StudyID = '20200101', '120000', '1'
        ds.SeriesNumber, ds.InstanceNumber = 1, z + 1
        ds.Rows = ds.Columns = 8
        ds.ImagePositionPatient = [0, 0, z * 2]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing, ds.SliceThickness = [1, 1], 2
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, 'MONOCHROME2'
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit, ds.PixelRepresentation = 15, 1
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        ds.PixelData = (np.arange(64, dtype=np.int16).reshape(8, 8) + z).tobytes()
        ds.save_as(ct / f'{z}.dcm', enforce_file_format=True)
    return ct


class EngineContractTests(unittest.TestCase):
    def test_qc_returns_only_selected_patients_with_json_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_scan(root / 'raw', 'A')
            write_scan(root / 'raw', 'B')
            with EngineWorkspace(root / 'raw', root / 'work') as engine:
                result = engine.run_stage('qc', ['B'])
                json.dumps(result, allow_nan=False)
                self.assertEqual(result['status'], 'success')
                self.assertEqual([p['patient_id'] for p in result['patients']], ['B'])
                patient = result['patients'][0]
                self.assertEqual(patient['status'], 'success')
                self.assertEqual(patient['values']['geometry']['passed'], True)
                self.assertEqual(patient['values']['anonymized']['passed'], True)
                self.assertEqual(patient['errors'], [])
                self.assertEqual(patient['artifacts'], [])

    def test_invalid_selection_and_scan_failures_keep_requested_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_scan(root / 'raw', 'good')
            broken = root / 'raw' / 'broken' / 'ct'
            broken.mkdir(parents=True)
            (broken / 'invalid.dcm').write_text('not DICOM')
            with EngineWorkspace(root / 'raw', root / 'work') as engine:
                empty = engine.run_stage('qc', [])
                self.assertEqual(empty['errors'][0]['code'], 'empty_selection')
                result = engine.run_stage('qc', ['broken', '../good', 'missing', 'good'])
                json.dumps(result, allow_nan=False)
                self.assertEqual(result['status'], 'partial')
                self.assertEqual([p['patient_id'] for p in result['patients']],
                                 ['broken', '../good', 'missing', 'good'])
                self.assertEqual([p['status'] for p in result['patients']],
                                 ['failed', 'failed', 'failed', 'success'])
                self.assertEqual(result['patients'][0]['errors'][0]['code'], 'processing_failed')
                self.assertEqual(result['patients'][2]['errors'][0]['code'], 'unknown_patient')

    def test_masks_and_features_return_real_artifacts_in_isolated_workspaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ct = write_scan(root / 'raw', 'A')
            rt = RTStructBuilder.create_new(dicom_series_path=str(ct))
            mask = np.zeros((8, 8, 4), dtype=bool)
            mask[2:6, 2:6, 1:3] = True
            rt.add_roi(mask=mask, name='GTV-1')
            rt.save(str(ct.parent / 'rtstruct.dcm'))
            with EngineWorkspace(root / 'raw', root / 'work') as first:
                first_path = first.path
                with EngineWorkspace(root / 'raw', root / 'work') as second:
                    second_path = second.path
                    result = first.run_stage('masks', ['A'])
                    other = second.run_stage('masks', ['A'])
                    json.dumps(result, allow_nan=False)
                    self.assertEqual(result['status'], 'success')
                    self.assertEqual(result['patients'][0]['values']['voxel_count'], 32)
                    artifact = result['patients'][0]['artifacts'][0]
                    self.assertEqual(artifact['media_type'], 'application/x-npy')
                    self.assertNotEqual(first.path, second.path)
                    self.assertTrue((first.path / artifact['path']).is_file())
                    self.assertTrue((second.path / other['patients'][0]['artifacts'][0]['path']).is_file())
                    features = first.run_stage('features', ['A'])
                    json.dumps(features, allow_nan=False)
                    self.assertEqual(features['status'], 'success')
                    # Symmetric tumor intensities have zero mean after configured normalization.
                    self.assertAlmostEqual(features['patients'][0]['values']['original_firstorder_Mean'], 0.0, places=6)
                self.assertFalse(second_path.exists())
                self.assertTrue(first_path.exists())
            self.assertFalse(first_path.exists())

    def test_patient_mask_failure_and_exception_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_scan(root / 'raw', 'A')
            with self.assertRaisesRegex(RuntimeError, 'caller failure'):
                with EngineWorkspace(root / 'raw', root / 'work') as engine:
                    path = engine.path
                    result = engine.run_stage('masks', ['A'])
                    self.assertEqual(result['patients'][0]['patient_id'], 'A')
                    self.assertEqual(result['patients'][0]['errors'][0]['code'], 'missing_rtstruct')
                    self.assertEqual(result['patients'][0]['artifacts'], [])
                    raise RuntimeError('caller failure')
            self.assertFalse(path.exists())

    def test_library_symlinks_cannot_read_another_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with EngineWorkspace(root / 'raw', root / 'work') as first:
                write_scan(first.path, 'A')
                (root / 'raw' / 'A').mkdir(parents=True)
                (root / 'raw' / 'A' / 'ct').symlink_to(first.path / 'A' / 'ct')
                with EngineWorkspace(root / 'raw', root / 'work') as second:
                    result = second.run_stage('qc', ['A'])
                    self.assertEqual(result['patients'][0]['status'], 'failed')
                    self.assertEqual(result['patients'][0]['errors'][0]['code'], 'unsafe_library_path')


if __name__ == '__main__':
    unittest.main()

class PublicPseudonymTests(unittest.TestCase):
    def test_known_public_pseudonym_is_allowed_but_unexpected_identifiers_alarm(self):
        import pydicom
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ct = write_scan(root / 'raw', 'LUNG1-001')
            for path in ct.glob('*.dcm'):
                ds = pydicom.dcmread(path)
                ds.PatientID = ds.PatientName = 'LUNG1-001'
                ds.save_as(path, enforce_file_format=True)
            with EngineWorkspace(root / 'raw', root / 'work') as engine:
                result = engine.run_stage('qc', ['LUNG1-001'])
                self.assertEqual(result['patients'][0]['status'], 'success')
            path = ct / '0.dcm'
            ds = pydicom.dcmread(path)
            ds.PatientName = 'SUSPECTED_PRIVATE_VALUE'
            ds.save_as(path, enforce_file_format=True)
            with EngineWorkspace(root / 'raw', root / 'work') as engine:
                result = engine.run_stage('qc', ['LUNG1-001'])
                self.assertEqual(result['patients'][0]['values']['anonymized']['passed'], False)
                self.assertNotIn('SUSPECTED_PRIVATE_VALUE', json.dumps(result))

            ds.PatientName = 'LUNG1-001'
            ds.PatientBirthDate = '20000101'
            ds.save_as(path, enforce_file_format=True)
            with EngineWorkspace(root / 'raw', root / 'work') as engine:
                result = engine.run_stage('qc', ['LUNG1-001'])
                self.assertEqual(result['patients'][0]['values']['anonymized']['passed'], False)
                self.assertNotIn('20000101', json.dumps(result))
