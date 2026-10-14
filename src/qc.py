"""Quality-control checks for DICOM CT series.

Every check returns (passed: bool, detail: str) so the full run can be written
to an audit log — the paper trail that matters in any medical-data context.
"""
import json

import numpy as np
import pydicom
from pathlib import Path

from . import config
from .dicom_loader import load_series

# Tags that must NOT carry real patient info in a research dataset
ANON_TAGS = ["PatientName", "PatientBirthDate"]


def check_geometry(meta):
    ok = meta["rows"] > 0 and meta["columns"] > 0 and meta["n_slices"] > 1
    return ok, f'{meta["rows"]}x{meta["columns"]}x{meta["n_slices"]}'


def check_slice_spacing(meta, max_jitter_mm):
    """Slices must be evenly spaced; jitter means a stretched/squished volume."""
    gaps = np.diff(np.array(meta["positions"]))
    jitter = float(np.max(np.abs(gaps - np.median(gaps)))) if len(gaps) else 0.0
    passed = jitter <= max_jitter_mm
    return passed, f"max spacing jitter {jitter:.3f} mm (limit {max_jitter_mm})"


def check_anonymized(first_slice, anon_tags=ANON_TAGS):
    leaks = [t for t in anon_tags if str(getattr(first_slice, t, "")).strip()]
    passed = not leaks
    return passed, ("clean" if passed else f"possible PHI in tags: {leaks}")


def run_qc(series_dir, max_jitter_mm=config.MAX_SPACING_JITTER_MM):
    """Run every check on one series directory. Returns a dict for the audit log."""
    dcm_files = sorted(Path(series_dir).glob("*.dcm"))
    first = pydicom.dcmread(str(dcm_files[0]))
    _, meta = load_series(series_dir)

    results = {"series_dir": str(series_dir), "patient_id": meta["patient_id"]}
    results["geometry"] = check_geometry(meta)
    results["slice_spacing"] = check_slice_spacing(meta, max_jitter_mm)
    results["anonymized"] = check_anonymized(first)
    results["passed_all"] = all(v[0] for v in
                                (results["geometry"], results["slice_spacing"],
                                 results["anonymized"]))
    return results


def qc_all(patient_dirs, log_path=config.QC_LOG):
    """Run QC over many patients, write the audit log, return (passed, failed)."""
    log, passed, failed = [], [], []
    for pdir in patient_dirs:
        try:
            r = run_qc(pdir)
        except Exception as e:  # noqa: BLE001 - a broken series is a QC failure, log it
            r = {"series_dir": str(pdir), "patient_id": "unknown",
                 "passed_all": False, "error": str(e)}
        log.append(r)
        (passed if r["passed_all"] else failed).append(pdir)

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # tuples aren't JSON-serializable; stringify the check details
    serializable = [
        {k: (f"{v[0]} | {v[1]}" if isinstance(v, tuple) else v) for k, v in r.items()}
        for r in log
    ]
    log_path.write_text(json.dumps(serializable, indent=2))
    print(f"QC: {len(passed)} passed, {len(failed)} failed -> {log_path}")
    return passed, failed
