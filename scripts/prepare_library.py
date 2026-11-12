"""Prepare the full downloaded IDC CT/RTSTRUCT collection; no network activity.

python -m scripts.prepare_library --raw-dir /path/data/raw --output-dir /path/data/processed/library-v1
"""
import argparse
import json
from pathlib import Path


def main():
    from src.preparation import prepare_collection
    import duckdb
    import idc_index_data
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    raw = args.raw_dir.resolve()
    rows = duckdb.connect().execute("""SELECT PatientID, StudyInstanceUID, Modality,
        SeriesInstanceUID, instanceCount, series_size_MB FROM read_parquet(?)
        WHERE collection_id='nsclc_radiomics' AND Modality IN ('CT','RTSTRUCT')
        ORDER BY PatientID, Modality, SeriesInstanceUID""",
        [str(idc_index_data.IDC_INDEX_PARQUET_FILEPATH)]).fetchall()
    if len(rows) != 844 or len({r[0] for r in rows}) != 422:
        raise SystemExit('IDC manifest differs from expected collection: review source version explicitly')
    manifest = []
    for patient, study, modality, series, n, mb in rows:
        directory = raw / 'nsclc_radiomics' / patient / study / f'{modality}_{series}'
        files = sorted(directory.glob('*.dcm'))
        manifest.append({'patient_id': patient, 'study_uid': study, 'modality': modality,
            'series_uid': series, 'expected_instances': n, 'expected_size_MB': mb,
            'files': [str(path) for path in files], 'source': 'IDC idc-index-data ' + idc_index_data.__version__})
    report = prepare_collection(manifest, raw / 'clinical.csv', args.output_dir,
                                workers=args.workers, seed=args.seed)
    print(json.dumps(report['counts'], indent=2), flush=True)


if __name__ == '__main__':
    main()
