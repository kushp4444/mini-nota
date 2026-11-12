"""PyRadiomics feature extraction: tumor mask -> ~100+ measurements.

Each row of the output CSV is one patient; each column is one quantitative
imaging biomarker (shape, first-order intensity, texture). This is the
open-source cousin of Altis's "thousands of prognostic imaging biomarkers".
"""
import numpy as np
import pandas as pd
import SimpleITK as sitk
from pathlib import Path
from radiomics import featureextractor, getFeatureClasses

from . import config


class FeatureError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def extract_one(image_volume, mask_volume, spacing, *, geometry=None):
    """Run the configured PyRadiomics pipeline on one patient.

    image_volume: 3D int16 CT in Hounsfield Units. mask_volume: 3D binary mask.
    spacing: voxel size in mm as (z, y, x) to match the numpy array order.
    """
    extractor = featureextractor.RadiomicsFeatureExtractor(
        str(config.PYRADIOMICS_CONFIG))

    if not np.isfinite(image_volume).all():
        raise FeatureError('invalid_feature_input', 'Non-finite image values prevent feature extraction')
    if extractor.settings.get('normalize') and np.std(image_volume) == 0:
        raise FeatureError('invalid_feature_input', 'Image has zero variance; configured normalization is undefined')

    # SimpleITK expects (x, y, z) spacing order; numpy arrays are (z, y, x)
    sitk_spacing = tuple(reversed(spacing))
    image = sitk.GetImageFromArray(image_volume)
    image.SetSpacing(sitk_spacing)
    mask = sitk.GetImageFromArray(mask_volume.astype(np.uint8))
    mask.SetSpacing(sitk_spacing)
    if geometry is not None:
        # Both arrays share the same verified LPS origin and x/y/z directions.
        for grid in (image, mask):
            grid.SetOrigin(tuple(geometry['origin_lps_mm']))
            grid.SetDirection(tuple(np.asarray(geometry['direction_lps']).ravel()))

    result = extractor.execute(image, mask)
    # Keep feature values; drop the diagnostics_ metadata entries
    expected = sorted(
        f'original_{group}_{name}'
        for group, enabled in extractor.enabledFeatures.items()
        for name, deprecated in getFeatureClasses()[group].getFeatureNames().items()
        if (name in enabled if enabled else not deprecated))
    actual = {k: v for k, v in result.items() if k.startswith('original_')}
    if sorted(actual) != expected:
        raise FeatureError('feature_schema_mismatch', 'Extracted features do not match the configured schema')
    values = {}
    for name in expected:
        value = np.real_if_close(actual[name])
        if np.iscomplexobj(value) or not np.isfinite(value):
            raise FeatureError('invalid_feature_value', f'Non-finite or non-real feature: {name}')
        values[name] = float(value)
    return values


def extract_all(patient_rows, output_csv=config.FEATURES_CSV):
    """patient_rows: list of dicts with patient_id, image, mask, spacing.

    Writes one CSV: rows = patients, columns = features. Returns the DataFrame.
    """
    records = []
    for row in patient_rows:
        feats = extract_one(row["image"], row["mask"],
                            row["spacing"], geometry=row.get("geometry"))
        feats["patient_id"] = row["patient_id"]
        records.append(feats)
        print(f"extracted {len(feats) - 1} features for {row['patient_id']}")

    df = pd.DataFrame(records)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"wrote {df.shape[0]} patients x {df.shape[1] - 1} features -> {output_csv}")
    return df
