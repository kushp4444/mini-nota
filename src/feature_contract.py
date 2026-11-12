"""Version the measurements by ordered schema, extraction code/config and dependencies."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
from . import config


def extraction_contract():
    return {'radiomics_config_sha256':hashlib.sha256(config.PYRADIOMICS_CONFIG.read_bytes()).hexdigest(),
            'source_sha256':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
                             for name in ('dicom_loader.py','masks.py','extract_features.py')},
            'dependencies':{name:importlib.metadata.version(name) for name in ('numpy','pyradiomics','SimpleITK','pydicom','rt-utils')}}


def feature_version(schema, contract=None):
    payload={'schema':schema,'extraction':contract or extraction_contract()}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
