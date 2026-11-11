"""Verified regular-grid DICOM geometry, with numpy axes (slice,row,column).

DICOM PixelSpacing is (row,column); ImageOrientationPatient's first vector
advances columns. Slices are ordered by projection on their shared normal,
never filenames, InstanceNumber, or an assumed patient z direction.
"""
from pathlib import Path
import numpy as np
import pydicom


class GeometryError(ValueError):
    """A safe, patient-independent explanation of unsupported scan geometry."""


def load_series(series_dir):
    files = [pydicom.dcmread(str(f)) for f in sorted(Path(series_dir).glob('*.dcm'))]
    if not files:
        raise GeometryError('No CT slices found')
    try:
        first = files[0]
        orientation = np.asarray(first.ImageOrientationPatient, dtype=float)
        spacing = np.asarray(first.PixelSpacing, dtype=float)
        col_direction, row_direction = orientation[:3], orientation[3:]
        normal = np.cross(col_direction, row_direction)
        if (orientation.shape != (6,) or not np.isfinite(orientation).all()
                or not np.allclose([np.linalg.norm(col_direction), np.linalg.norm(row_direction)], 1, atol=1e-5)
                or abs(np.dot(col_direction, row_direction)) > 1e-5):
            raise GeometryError('Invalid image orientation')
        if spacing.shape != (2,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
            raise GeometryError('Missing or invalid in-plane spacing')
        identities = (str(first.SeriesInstanceUID), str(first.FrameOfReferenceUID), str(first.StudyInstanceUID))
        seen = set()
        for ds in files:
            if (ds.Modality != 'CT' or getattr(ds, 'NumberOfFrames', 1) != 1
                    or (int(ds.Rows), int(ds.Columns)) != (int(first.Rows), int(first.Columns))
                    or not np.allclose(ds.ImageOrientationPatient, orientation, atol=1e-5)
                    or not np.allclose(ds.PixelSpacing, spacing, atol=1e-5)
                    or (str(ds.SeriesInstanceUID), str(ds.FrameOfReferenceUID), str(ds.StudyInstanceUID)) != identities):
                raise GeometryError('Slices do not share compatible CT geometry')
            if str(ds.SOPInstanceUID) in seen:
                raise GeometryError('Duplicate slice identity')
            seen.add(str(ds.SOPInstanceUID))
            position = np.asarray(ds.ImagePositionPatient, dtype=float)
            if position.shape != (3,) or not np.isfinite(position).all():
                raise GeometryError('Invalid slice position')
        files.sort(key=lambda ds: float(np.dot(normal, ds.ImagePositionPatient)))
        origins = np.asarray([ds.ImagePositionPatient for ds in files], dtype=float)
        positions = origins @ normal
        if len(files) < 2:
            raise GeometryError('At least two CT slices are required to verify slice spacing')
        gaps = np.diff(positions)
        dz = float(np.median(gaps))
        if dz <= 0 or not np.allclose(gaps, dz, atol=.01, rtol=0):
            raise GeometryError('Nonuniform or duplicate slice spacing')
        if not np.allclose(origins - origins[0], np.outer(positions - positions[0], normal), atol=.01, rtol=0):
            raise GeometryError('Unsupported sheared CT grid (in-plane slice displacement)')
        # Each slice can have its own rescale, including negative or fractional HU.
        volume = np.stack([ds.pixel_array.astype(np.float32) * float(ds.RescaleSlope)
                           + float(ds.RescaleIntercept) for ds in files])
        if not np.isfinite(volume).all():
            raise GeometryError('Non-finite CT intensities')
        meta = {'n_slices': len(files), 'rows': int(first.Rows), 'columns': int(first.Columns),
                'slice_thickness': float(getattr(first, 'SliceThickness', dz)),
                'positions': positions.tolist(), 'patient_id': str(getattr(first, 'PatientID', 'unknown')),
                'spacing': [dz, float(spacing[0]), float(spacing[1])],
                'axis_order': 'zyx', 'origin_lps_mm': origins[0].tolist(),
                'direction_lps': np.column_stack((col_direction, row_direction, normal)).tolist(),
                'slice_origins_lps_mm': origins.tolist(),
                'sop_instance_uids': [str(ds.SOPInstanceUID) for ds in files],
                'series_instance_uid': identities[0], 'frame_of_reference_uid': identities[1],
                'geometry_verified': True}
        return volume, meta
    except GeometryError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise GeometryError('Required CT geometry or intensity metadata is missing or invalid') from exc
