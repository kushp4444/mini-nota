"""Selected-patient imaging tools; all generated files have temporary ownership.

Use one EngineWorkspace context per invocation. Consume/copy artifacts before
leaving the context: paths and the workspace are removed on success or failure.
"""
import csv
import hashlib
import json
import math

import numpy as np

from pathlib import Path
from tempfile import TemporaryDirectory

from .qc import run_qc
from .dicom_loader import load_series, GeometryError
from .masks import rtstruct_to_mask, MaskError
from PIL import Image
from .extract_features import extract_one, FeatureError


class EngineWorkspace:
    """Run real imaging stages against an immutable library and private workspace."""

    def __init__(self, raw_dir, workspace):
        self.raw_dir = Path(raw_dir).resolve()
        self.workspace_parent = Path(workspace).resolve()
        self.path = None

    def __enter__(self):
        self.workspace_parent.mkdir(parents=True, exist_ok=True)
        self._temporary = TemporaryDirectory(prefix='engine-', dir=self.workspace_parent)
        self.path = Path(self._temporary.name)
        return self

    def __exit__(self, *exc):
        self._temporary.cleanup()
        self.path = None

    def run_stage(self, stage, patient_ids, *, roi_name="GTV-1"):
        """Return a JSON-compatible result in requested patient order."""
        if self.path is None:
            raise RuntimeError('Use EngineWorkspace as a context manager')
        result = {'schema_version': 1, 'stage': stage, 'status': 'failed',
                  'patients': [], 'errors': []}
        if stage not in ('qc', 'masks', 'features'):
            result['errors'].append(_error('unknown_stage', 'Unsupported imaging stage'))
            return result
        if not patient_ids:
            result['errors'].append(_error('empty_selection', 'Select at least one patient'))
            return result
        for patient_id in patient_ids:
            patient = {'patient_id': patient_id, 'status': 'failed',
                       'values': {}, 'artifacts': [], 'errors': []}
            result['patients'].append(patient)
            # Never resolve caller-supplied paths outside the library.
            if (not isinstance(patient_id, str) or not patient_id
                    or Path(patient_id).name != patient_id or patient_id in ('.', '..')
                    or (self.raw_dir / patient_id).is_symlink()
                    or not (self.raw_dir / patient_id).is_dir()):
                patient['errors'].append(_error('unknown_patient', 'Patient is not in the library'))
                continue
            try:
                if any(path.is_symlink() for path in (self.raw_dir / patient_id).rglob('*')):
                    patient['errors'].append(_error('unsafe_library_path', 'Library entries must not link outside their patient'))
                    continue
                ct = self.raw_dir / patient_id / 'ct'
                if stage == 'qc':
                    checks = run_qc(ct)
                    patient['values'] = {
                        key: {'passed': bool(checks[key][0]), 'detail': checks[key][1]}
                        for key in ('geometry', 'slice_spacing', 'anonymized')}
                    if not checks['passed_all']:
                        patient['errors'].append(_error('qc_failed', 'Scan failed quality checks'))
                else:
                    if not (ct.parent / 'rtstruct.dcm').is_file():
                        patient['errors'].append(_error('missing_rtstruct', 'Patient has no RTSTRUCT'))
                        continue
                    image, meta = load_series(ct)
                    # The corrected RTSTRUCT adapter returns (row,column,slice); CT is (slice,row,column).
                    mask = np.transpose(rtstruct_to_mask(
                        ct, ct.parent / 'rtstruct.dcm', roi_name, geometry=meta), (2, 0, 1))
                    if mask.shape != image.shape:
                        raise ValueError('Image-mask shape mismatch')
                    directory = self.path / stage
                    directory.mkdir(exist_ok=True)
                    # Artifact names derive from validated library IDs only.
                    if stage == 'masks':
                        path = directory / f'{patient_id}.npy'
                        np.save(path, mask.astype(np.uint8))
                        tumor_slices = np.flatnonzero(mask.any(axis=(1, 2)))
                        middle = int(tumor_slices[len(tumor_slices) // 2])
                        patient['values'] = {'voxel_count': int(mask.sum()),
                            'volume_cm3': float(mask.sum() * np.prod(meta['spacing']) / 1000),
                            'shape': list(mask.shape), 'axis_order': 'zyx',
                            'spacing_mm': meta['spacing'], 'slice_index': middle,
                            'geometry': {k: meta[k] for k in ('origin_lps_mm', 'direction_lps', 'geometry_verified')}}
                        # Fixed lung window (-1000..400 HU), native row/column pixels.
                        gray = (np.clip((image[middle] + 1000) / 1400, 0, 1) * 255).astype(np.uint8)
                        rgb = np.repeat(gray[..., None], 3, axis=2)
                        rgb[mask[middle]] = (rgb[mask[middle]] * .55 + np.array([255,100,32]) * .45).astype(np.uint8)
                        overlay_path = directory / f'{patient_id}-overlay.png'
                        Image.fromarray(rgb).save(overlay_path, format='PNG')
                        media_type = 'application/x-npy'
                    else:
                        spacing = meta['spacing']
                        values = extract_one(image, mask, spacing, geometry=meta)
                        if not all(math.isfinite(value) for value in values.values()):
                            raise ValueError('Non-finite feature value')
                        patient['values'] = values
                        patient['feature_schema'] = list(values)
                        csv_path = directory / f'{patient_id}.csv'
                        with csv_path.open('w', newline='') as stream:
                            writer = csv.DictWriter(stream, fieldnames=['patient_id', *values])
                            writer.writeheader()
                            writer.writerow({'patient_id': patient_id, **values})
                        path = directory / f'{patient_id}.json'
                        path.write_text(json.dumps(values, allow_nan=False))
                        media_type = 'application/json'
                    patient['artifacts'] = [{
                        'path': str(path.relative_to(self.path)), 'media_type': media_type,
                        'role': 'mask' if stage == 'masks' else 'features',
                        'size_bytes': path.stat().st_size,
                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]
                    if stage == 'features':
                        patient['artifacts'].append({'path': str(csv_path.relative_to(self.path)),
                            'role': 'feature_csv', 'media_type': 'text/csv', 'size_bytes': csv_path.stat().st_size,
                            'sha256': hashlib.sha256(csv_path.read_bytes()).hexdigest()})
                    if stage == 'masks':
                        patient['artifacts'].append({'path': str(overlay_path.relative_to(self.path)),
                            'role': 'overlay', 'media_type': 'image/png', 'size_bytes': overlay_path.stat().st_size,
                            'sha256': hashlib.sha256(overlay_path.read_bytes()).hexdigest()})
                patient['status'] = 'failed' if patient['errors'] else 'success'
            except (GeometryError, MaskError, FeatureError) as exc:
                patient['errors'].append(_error(getattr(exc, 'code', 'unsupported_geometry'), str(exc)))
            except Exception as exc:
                # Retain identity from the selection, never from a malformed header.
                patient['errors'].append(_error('processing_failed',
                                                'Patient stage processing failed', type(exc).__name__))
        successes = sum(p['status'] == 'success' for p in result['patients'])
        result['status'] = ('success' if successes == len(result['patients']) else
                            'partial' if successes else 'failed')
        return result


def _error(code, message, error_type=None):
    error = {'code': code, 'message': message}
    if error_type:
        error['type'] = error_type
    return error
