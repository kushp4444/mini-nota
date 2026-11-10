"""Fetch the Lung1 clinical table from IDC and save data/raw/clinical.csv.

Run from the repo root:
    python scripts/fetch_clinical.py
"""
from pathlib import Path
from idc_index import IDCClient

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

client = IDCClient.client()
client.fetch_index("clinical_index")

tables = client.sql_query("SELECT DISTINCT table_name FROM clinical_index")
hits = tables[tables["table_name"].str.endswith("nsclc_radiomics_clinical")]
print("candidate tables:")
print(hits.to_string())
if hits.empty:
    raise SystemExit("no nsclc/lung1 clinical table found - inspect `tables` above")

table = hits["table_name"].iloc[0]
print(f"\nusing table: {table}")
short = table.split(".")[-1]  # local dir uses the short name
print(f"local name: {short}")
clin = client.get_clinical_table(short)
if clin is None:
    raise SystemExit(f"table {table} has no downloadable data")
print("columns:", list(clin.columns))

# normalize the id column: IDC uses dicom_patient_id / patientid;
# the pipeline joins on lowercase patient_id
if "dicom_patient_id" in clin.columns:
    clin = clin.rename(columns={"dicom_patient_id": "patient_id"})
elif "patientid" in clin.columns:
    clin = clin.rename(columns={"patientid": "patient_id"})
elif "PatientID" in clin.columns:
    clin = clin.rename(columns={"PatientID": "patient_id"})
print("id sample:", clin["patient_id"].astype(str).head(5).tolist())
clin.to_csv(RAW_DIR / "clinical.csv", index=False)
print(f"saved -> {RAW_DIR / 'clinical.csv'} ({len(clin)} rows)")

# cross-check: every downloaded patient should have a clinical row
imaging_ids = {p.name for p in RAW_DIR.iterdir() if p.is_dir() and (p / "ct").exists()}
clinical_ids = set(clin["patient_id"].astype(str))
print(f"\nimaging patients: {len(imaging_ids)}, clinical rows: {len(clinical_ids)}")
print(f"matched in both: {len(imaging_ids & clinical_ids)}")
missing = sorted(imaging_ids - clinical_ids)
if missing:
    print(f"WARNING - imaging patients with no clinical row (dropped at survival stage): {missing}")
else:
    print("all imaging patients have clinical rows")
