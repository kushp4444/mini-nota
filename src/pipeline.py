"""CLI entry point tying the mini-nota stages together.

    python -m src.pipeline --stage qc       --data data/raw --subset 30
    python -m src.pipeline --stage masks     --data data/raw --subset 30
    python -m src.pipeline --stage features  --data data/raw --subset 30
    python -m src.pipeline --stage survival  --duration-col T --event-col E

Run from the repo root. Start with --subset while iterating; drop it to go full.
"""
import argparse
import numpy as np
from pathlib import Path

from . import config
from .dicom_loader import load_series
from .qc import qc_all
from .masks import list_rois, rtstruct_to_mask
from .extract_features import extract_all
from .survival import run_survival


def iter_patients(raw_dir, subset=None):
    """Yield (patient_id, ct_dir, rtstruct_path) per patient.

    Assumes data/raw/<PATIENT_ID>/{ct/, rtstruct.dcm} (see data/README.md).
    Adjust this function if your download layout differs.
    """
    raw_dir = Path(raw_dir)
    patient_dirs = sorted(p for p in raw_dir.iterdir()
                          if p.is_dir() and (p / "ct").exists())
    if subset:
        patient_dirs = patient_dirs[:subset]
    for pdir in patient_dirs:
        rt = pdir / "rtstruct.dcm"
        yield pdir.name, pdir / "ct", (rt if rt.exists() else None)


def main():
    ap = argparse.ArgumentParser(description="mini-nota pipeline")
    ap.add_argument("--stage", required=True,
                    choices=["qc", "masks", "features", "survival"])
    ap.add_argument("--data", default=str(config.RAW_DIR))
    ap.add_argument("--subset", type=int, default=None,
                    help="only process the first N patients (iterate fast)")
    ap.add_argument("--roi", default="GTV-1",
                    help="tumor ROI name in the RTSTRUCT (verify with list_rois first)")
    ap.add_argument("--duration-col", default="REPLACE_WITH_YOUR_TIME_COLUMN")
    ap.add_argument("--event-col", default="REPLACE_WITH_YOUR_EVENT_COLUMN")
    args = ap.parse_args()

    patients = list(iter_patients(args.data, args.subset))
    print(f"{len(patients)} patients")

    if args.stage == "qc":
        qc_all([ct for _, ct, _ in patients])

    elif args.stage == "masks":
        pid, ct, rt = patients[0]
        print("First patient ROI names (confirm --roi against these):")
        list_rois(ct, rt)
        for pid, ct, rt in patients:
            if rt is None:
                print(f"SKIP {pid}: no rtstruct file")
                continue
            rtstruct_to_mask(ct, rt, args.roi)
            # NOTE: masks are recomputed in the features stage; this stage is
            # for verifying ROI names and alignment before the long batch run.

    elif args.stage == "features":
        rows = []
        for pid, ct, rt in patients:
            if rt is None:
                print(f"SKIP {pid}: no rtstruct file")
                continue
            image, meta = load_series(ct)
            mask = np.transpose(rtstruct_to_mask(ct, rt, args.roi, geometry=meta), (2, 0, 1))
            spacing = meta["spacing"]
            rows.append({"patient_id": pid, "image": image,
                         "mask": mask, "spacing": spacing, "geometry": meta})
        extract_all(rows)

    elif args.stage == "survival":
        run_survival(duration_col=args.duration_col, event_col=args.event_col)


if __name__ == "__main__":
    main()
