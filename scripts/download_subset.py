"""Download a 30-patient CT + RTSTRUCT subset of NSCLC-Radiomics via IDC.

Run from the repo root with the venv active:
    python scripts/download_subset.py
"""
from pathlib import Path
from idc_index import IDCClient

N_PATIENTS = 30
COLLECTION_ID = "nsclc_radiomics"

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

client = IDCClient.client()

df = client.sql_query(f"""
    SELECT PatientID, Modality, SeriesInstanceUID
    FROM index
    WHERE collection_id = '{COLLECTION_ID}'
      AND Modality IN ('CT', 'RTSTRUCT')
""")
if df.empty:
    raise SystemExit(
        "query returned 0 rows - wrong collection_id? "
        "run client.get_collections() to see the exact ids"
    )

patients = sorted(df["PatientID"].unique())[:N_PATIENTS]
sub = df[df["PatientID"].isin(patients)]
uids = sub["SeriesInstanceUID"].tolist()
n_ct = (sub["Modality"] == "CT").sum()
n_rt = (sub["Modality"] == "RTSTRUCT").sum()
print(f"{len(patients)} patients, {len(uids)} series ({n_ct} CT, {n_rt} RTSTRUCT)")

client.download_dicom_series(seriesInstanceUID=uids, downloadDir=str(RAW_DIR))
print(f"done -> {RAW_DIR}")
