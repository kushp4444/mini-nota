"""Reshape the IDC download layout into what src/pipeline.py expects:

    from: data/raw/nsclc_radiomics/<PATIENT>/<study>/<MODALITY>_<series>/*.dcm
    to:   data/raw/<PATIENT>/{ct/*.dcm, rtstruct.dcm}

Run from the repo root:
    python scripts/reorganize.py
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SRC = RAW_DIR / "nsclc_radiomics"

assert SRC.is_dir(), f"no download found at {SRC} - run download_subset.py first"

for patient_dir in sorted(SRC.iterdir()):
    if not patient_dir.is_dir():
        continue
    pid = patient_dir.name
    dest = RAW_DIR / pid
    ct_dest = dest / "ct"
    ct_dest.mkdir(parents=True, exist_ok=True)

    ct_series = sorted(d for d in patient_dir.rglob("CT_*") if d.is_dir())
    rt_series = sorted(d for d in patient_dir.rglob("RTSTRUCT_*") if d.is_dir())
    if not ct_series:
        print(f"SKIP {pid}: no CT series found")
        continue
    if len(ct_series) > 1:
        print(f"WARN {pid}: {len(ct_series)} CT series, using first")
    for f in ct_series[0].glob("*.dcm"):
        shutil.copy(f, ct_dest / f.name)

    if rt_series:
        if len(rt_series) > 1:
            print(f"WARN {pid}: {len(rt_series)} RTSTRUCT series, using first")
        rt_files = list(rt_series[0].glob("*.dcm"))
        shutil.copy(rt_files[0], dest / "rtstruct.dcm")
    else:
        print(f"WARN {pid}: no RTSTRUCT found (pipeline will skip this patient)")

done = sorted(p.name for p in RAW_DIR.iterdir() if p.is_dir() and (p / "ct").exists())
print(f"\n{len(done)} patient dirs ready: {done[:5]}{'...' if len(done) > 5 else ''}")
