"""Convert a doctor's RTSTRUCT tumor outline into a 3D binary mask.

RTSTRUCT stores the tumor as contour lines drawn on each slice. PyRadiomics
needs a voxel mask (1 = tumor, 0 = background) aligned with the CT volume,
so we rasterize the contours with rt-utils.

In NSCLC-Radiomics the tumor ROI is typically named like "GTV-1" — always
verify with list_rois() on your first patient before batching.
"""
from rt_utils import RTStructBuilder


def list_rois(dicom_series_dir, rtstruct_path):
    """Print the named regions in an RTSTRUCT file so you can pick the tumor one."""
    builder = RTStructBuilder.create_from(
        dicom_series_path=str(dicom_series_dir),
        rt_struct_path=str(rtstruct_path),
    )
    names = builder.get_roi_names()
    print("ROIs found:", names)
    return names


def rtstruct_to_mask(dicom_series_dir, rtstruct_path, roi_name):
    """Rasterize one ROI's contours into a 3D numpy mask aligned with the CT."""
    builder = RTStructBuilder.create_from(
        dicom_series_path=str(dicom_series_dir),
        rt_struct_path=str(rtstruct_path),
    )
    mask = builder.get_roi_mask_by_name(roi_name)
    assert mask.ndim == 3 and mask.sum() > 0, f"empty mask for ROI {roi_name}"
    print(f"mask for {roi_name}: shape {mask.shape}, {int(mask.sum())} tumor voxels")
    return mask
