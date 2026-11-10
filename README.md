# mini-nota

A toy-scale replica of Altis Labs' IPRO pipeline: CT scans in, survival prediction out.

**What this is:** a proof of work showing the *shape* of imaging-based survival
prediction — DICOM ingestion + QC, radiomic feature extraction, survival analysis —
built on public lung-cancer data. It mirrors the engineering problems Altis hires for:
data quality at ingest, reproducible feature pipelines, rigorous model evaluation.

**What it is not:** medical advice, a clinical tool, a reproduction of Altis's
proprietary model, or affiliated with Altis Labs in any way.

## The pipeline

1. **Ingest + QC** (`src/dicom_loader.py`, `src/qc.py`) — load DICOM series into 3D
   volumes, validate slice geometry / spacing / anonymization, write an audit log.
2. **Masks** (`src/masks.py`) — convert the doctor-drawn RTSTRUCT tumor outlines into
   3D binary masks aligned with the CT volume.
3. **Features** (`src/extract_features.py`) — PyRadiomics extracts ~100+ shape, texture,
   and intensity measurements per tumor → `outputs/features.csv`.
4. **Survival** (`src/survival.py`) — Cox proportional-hazards model via `lifelines`;
   concordance index + Kaplan-Meier curves → `outputs/kaplan_meier.png`.

## Data

Public **NSCLC-Radiomics** collection from The Cancer Imaging Archive (TCIA):
CT scans + survival outcomes + tumor segmentations for ~422 lung cancer patients.
See `data/README.md` for download instructions. Raw data is git-ignored — never commit it.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run (start small, then scale)

```bash
# 1. QC a 30-patient subset while iterating
python -m src.pipeline --stage qc --data data/raw --subset 30

# 2. Build tumor masks
python -m src.pipeline --stage masks --data data/raw --subset 30

# 3. Extract radiomic features
python -m src.pipeline --stage features --data data/raw --subset 30

# 4. Survival analysis -> outputs/kaplan_meier.png
python -m src.pipeline --stage survival
```

## Project layout

```
mini-nota/
├── src/
│   ├── config.py            # paths, thresholds, constants
│   ├── dicom_loader.py      # DICOM series -> 3D numpy volume (Hounsfield units)
│   ├── qc.py                # geometry / spacing / anonymization checks + audit log
│   ├── masks.py             # RTSTRUCT contours -> 3D binary tumor mask
│   ├── extract_features.py  # PyRadiomics -> features CSV
│   ├── survival.py          # Cox model + Kaplan-Meier (lifelines)
│   └── pipeline.py          # CLI entry point tying the stages together
├── data/
│   └── README.md            # how to download the TCIA dataset (data itself is ignored)
├── outputs/                 # features.csv, QC log, KM plot (git-ignored)
├── pyradiomics_config.yaml  # which features to extract and how
└── requirements.txt
```

## Honest limitations

- Toy scale, public data, open-source features — this demonstrates understanding of the
  *shape* of the problem, not Altis's proprietary IPRO.
- No claim of clinical validity. The point is the engineering: clean ingestion,
  auditable QC, reproducible evaluation.
