"""RTSTRUCT tumor rasterization on the verified CT grid.

Use rt-utils for RTSTRUCT validation and ROI/contour selection. Correct its
1.2.x rasterizer's swapped in-plane spacing and rectangular-image allocation:
OpenCV points are (column,row), output axes here are (row,column,slice).
"""
import cv2
import numpy as np
from rt_utils import RTStructBuilder, ds_helper
from .dicom_loader import load_series


class MaskError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def list_rois(dicom_series_dir, rtstruct_path):
    return RTStructBuilder.create_from(str(dicom_series_dir), str(rtstruct_path)).get_roi_names()


def rtstruct_to_mask(dicom_series_dir, rtstruct_path, roi_name, *, geometry=None):
    if geometry is None:
        _, geometry = load_series(dicom_series_dir)
    try:
        builder = RTStructBuilder.create_from(str(dicom_series_dir), str(rtstruct_path))
    except Exception as exc:
        raise MaskError('invalid_rtstruct', 'RTSTRUCT is invalid or references another CT series') from exc
    matching = [roi for roi in builder.ds.StructureSetROISequence if roi.ROIName == roi_name]
    if not matching:
        raise MaskError('missing_roi', 'Requested tumor ROI is absent')
    if len(matching) != 1:
        raise MaskError('ambiguous_roi', 'Tumor ROI name is ambiguous')
    roi = matching[0]
    if str(getattr(roi, 'ReferencedFrameOfReferenceUID', '')) != geometry['frame_of_reference_uid']:
        raise MaskError('mask_misaligned', 'Tumor ROI frame of reference does not match CT')
    refs = getattr(builder.ds, 'ReferencedFrameOfReferenceSequence', [])
    if not refs or any(str(getattr(ref, 'FrameOfReferenceUID', '')) != geometry['frame_of_reference_uid'] for ref in refs):
        raise MaskError('mask_misaligned', 'RTSTRUCT frame of reference does not match CT')
    for frame in refs:
        for study in getattr(frame, 'RTReferencedStudySequence', []):
            for series in getattr(study, 'RTReferencedSeriesSequence', []):
                if str(series.SeriesInstanceUID) != geometry['series_instance_uid']:
                    raise MaskError('mask_misaligned', 'RTSTRUCT references a different CT series')
    roi_contours = [entry for entry in builder.ds.ROIContourSequence
                    if str(entry.ReferencedROINumber) == str(roi.ROINumber)]
    if not roi_contours or not getattr(roi_contours[0], 'ContourSequence', []):
        raise MaskError('empty_mask', 'Tumor ROI contains no contours')
    contours = ds_helper.get_contour_sequence_by_roi_number(builder.ds, roi.ROINumber)
    shape = (geometry['n_slices'], geometry['rows'], geometry['columns'])
    mask = np.zeros(shape, dtype=np.uint8)
    direction = np.asarray(geometry['direction_lps'])
    col_direction, row_direction, normal = direction.T
    spacing = geometry['spacing']
    uids = geometry['sop_instance_uids']
    for contour in contours:
        if str(getattr(contour, 'ContourGeometricType', '')) != 'CLOSED_PLANAR':
            raise MaskError('unsupported_contour', 'Only closed planar tumor contours are supported')
        images = getattr(contour, 'ContourImageSequence', [])
        if len(images) != 1 or str(images[0].ReferencedSOPInstanceUID) not in uids:
            raise MaskError('mask_misaligned', 'Tumor contour does not reference exactly one selected CT slice')
        index = uids.index(str(images[0].ReferencedSOPInstanceUID))
        try:
            coords = np.asarray(contour.ContourData, dtype=float).reshape(-1, 3)
        except (AttributeError, TypeError, ValueError) as exc:
            raise MaskError('invalid_contour', 'Tumor contour has invalid coordinates') from exc
        if len(coords) < 3 or len(coords) != int(contour.NumberOfContourPoints) or not np.isfinite(coords).all():
            raise MaskError('invalid_contour', 'Tumor contour has invalid coordinates')
        delta = coords - np.asarray(geometry['slice_origins_lps_mm'][index])
        if np.max(np.abs(delta @ normal)) > .01:
            raise MaskError('mask_misaligned', 'Tumor contour is not on its referenced CT slice plane')
        xy = np.column_stack((delta @ col_direction / spacing[2], delta @ row_direction / spacing[1]))
        if (np.any(xy < -.5) or np.any(xy[:,0] > shape[2] - .5) or np.any(xy[:,1] > shape[1] - .5)):
            raise MaskError('mask_misaligned', 'Tumor contour extends outside the selected CT grid')
        # Separate polygons use XOR, preserving nested holes and disconnected regions.
        polygon = np.zeros(shape[1:], dtype=np.uint8)
        cv2.fillPoly(polygon, [np.rint(xy).astype(np.int32)], 1)
        mask[index] ^= polygon
    if not mask.any():
        raise MaskError('empty_mask', 'Tumor ROI contains no tumor voxels')
    return mask.transpose(1, 2, 0).astype(bool)
