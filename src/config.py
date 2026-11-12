"""Central configuration: paths, thresholds, constants.

Everything path-related lives here so no module hardcodes locations.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"            # TCIA download lands here (git-ignored)
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = ROOT / "outputs"

# Resolve default paths without writing to the application tree. Stage writers
# create their own output directories only when an operation requests output.

PYRADIOMICS_CONFIG = ROOT / "pyradiomics_config.yaml"

FEATURES_CSV = OUTPUTS_DIR / "features.csv"
QC_LOG = OUTPUTS_DIR / "qc_log.json"
KM_PLOT = OUTPUTS_DIR / "kaplan_meier.png"

# QC thresholds
MAX_SPACING_JITTER_MM = 0.5  # flag series whose slice spacing varies more than this

# Survival analysis
RANDOM_STATE = 42
TEST_SIZE = 0.25
COX_PENALIZER = 0.1  # L2 shrinkage: 100+ features on ~422 patients needs regularization
