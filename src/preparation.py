"""Offline, model-independent collection preparation. Never called by visitor runs."""
import hashlib
import json
import re


def freeze_partition(records, *, seed=42, held_out_fraction=.2):
    """Hash-order within event strata; one immutable patient assignment, no score search."""
    ids = [r['patient_id'] for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate patient identities')
    if not 0 < held_out_fraction < 1:
        raise ValueError('held_out_fraction must lie between zero and one')
    strata = {}
    for row in records:
        if row['scoring_eligible']:
            event = str(row['outcome']['event']) if row.get('outcome') else 'missing_outcome'
            strata.setdefault(event, []).append(row['patient_id'])
    development, held_out = [], []
    counts = {}
    for event, members in sorted(strata.items()):
        members.sort(key=lambda patient: (hashlib.sha256(f'{seed}:{patient}'.encode()).hexdigest(), patient))
        n = int(len(members) * held_out_fraction + .5)
        if len(members) > 1:
            n = min(len(members) - 1, max(1, n))
        held_out.extend(members[:n])
        development.extend(members[n:])
        counts[event] = {'development': len(members) - n, 'held_out': n}
    return {'schema_version': 1, 'seed': seed, 'held_out_fraction': held_out_fraction,
            'method': 'sha256(seed:patient_id) ordering within observed event/missing-outcome strata; nearest integer allocation',
            'development': sorted(development), 'held_out': sorted(held_out), 'strata': counts}


def _json(path, value):
    from pathlib import Path
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


def _sha(path):
    from pathlib import Path
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _outcomes(path):
    import csv
    import math
    rows = {}
    for row in csv.DictReader(open(path)):
        patient = row['patient_id']
        rows.setdefault(patient, []).append(row)
    result = {}
    for patient, matches in rows.items():
        errors, outcome = [], None
        if not re.fullmatch(r'LUNG1-\d{3}', patient):
            errors.append({'code': 'invalid_outcome_identifier', 'message': 'Clinical identifier is not a Lung1 pseudonym'})
        if len(matches) != 1:
            errors.append({'code': 'duplicate_outcome', 'message': 'Multiple outcome records for patient'})
        else:
            row = matches[0]
            if row.get('patientid', patient) != patient:
                errors.append({'code': 'outcome_identifier_mismatch', 'message': 'Clinical identifier columns disagree'})
            try:
                duration = float(row['survivaltime'])
                assert math.isfinite(duration) and duration > 0
            except (ValueError, TypeError, AssertionError):
                errors.append({'code': 'invalid_duration', 'message': 'Survival duration must be finite and positive (days)'})
            try:
                event = float(row['deadstatusevent'])
                assert event in (0, 1)
            except (ValueError, TypeError, AssertionError):
                errors.append({'code': 'invalid_event', 'message': 'Observed event must be encoded as 0 or 1'})
            if not errors:
                outcome = {'duration': duration, 'event': int(event), 'time_unit': 'days'}
        result[patient] = (outcome, errors)
    return result


def _prepare_patient(job):
    """One bounded process owns at most one patient's CT/resampling allocations."""
    import os
    import shutil
    from pathlib import Path
    import pydicom
    import SimpleITK as sitk
    from threadpoolctl import threadpool_limits
    from .engine import EngineWorkspace
    from .qc import check_anonymized
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(1)
    threadpool_limits(limits=1)
    patient, entries, output, outcome_data = job
    output = Path(output)
    record = {'patient_id': patient, 'scoring_eligible': False,
              'outcome': outcome_data[0], 'evaluation_exclusions': outcome_data[1],
              'processing_exclusions': [], 'stages': {}, 'sources': []}
    try:
        if not re.fullmatch(r'LUNG1-\d{3}', patient) or not 1 <= int(patient[-3:]) <= 422:
            raise ValueError('invalid_patient_identifier')
        candidates = {'CT': [], 'RTSTRUCT': []}
        sops = set()
        for entry in entries:
            headers = []
            for filename in sorted(entry['files']):
                path = Path(filename)
                ds = pydicom.dcmread(path, stop_before_pixels=True)
                if str(getattr(ds, 'PatientID', '')) != patient:
                    raise ValueError('source_patient_identifier_mismatch')
                if str(getattr(ds, 'SeriesInstanceUID', '')) != entry['series_uid'] or ds.Modality != entry['modality']:
                    raise ValueError('source_series_identifier_mismatch')
                if not check_anonymized(ds, public_patient_id=patient)[0]:
                    raise ValueError('source_anonymization_alarm')
                sop = str(ds.SOPInstanceUID)
                if sop in sops:
                    raise ValueError('duplicate_source_instance')
                sops.add(sop)
                headers.append(ds)
                record['sources'].append({'path': str(path), 'sop_instance_uid': sop,
                    'series_uid': entry['series_uid'], 'size_bytes': path.stat().st_size, 'sha256': _sha(path)})
            candidates[entry['modality']].append((entry, headers))
        # Never choose the first filesystem series. Ambiguous alternatives require review.
        if len(candidates['CT']) != 1 or len(candidates['RTSTRUCT']) != 1:
            raise ValueError('ambiguous_or_missing_series')
        ct_entry, ct_headers = candidates['CT'][0]
        rt_entry, rt_headers = candidates['RTSTRUCT'][0]
        if len(rt_headers) != 1:
            raise ValueError('ambiguous_rtstruct_instances')
        record['selection'] = {'ct_series_uid': ct_entry['series_uid'], 'rtstruct_series_uid': rt_entry['series_uid'], 'roi_name': 'GTV-1'}
        destination = output / 'raw' / patient
        (destination / 'ct').mkdir(parents=True, exist_ok=True)
        for i, source in enumerate(sorted(ct_entry['files'])):
            target = destination / 'ct' / f'{i:05}.dcm'
            if not target.exists():
                os.link(source, target)
        target = destination / 'rtstruct.dcm'
        if not target.exists():
            os.link(rt_entry['files'][0], target)
        with EngineWorkspace(output / 'raw', output / 'temporary') as engine:
            for stage in ('qc', 'masks', 'features'):
                measured = engine.run_stage(stage, [patient])['patients'][0]
                for artifact in measured['artifacts']:
                    # Retain compact measured display/features only, not full NPY masks.
                    if artifact['role'] == 'mask':
                        continue
                    target = output / 'artifacts' / patient / Path(artifact['path']).name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(engine.path / artifact['path'], target)
                    artifact['path'] = str(target.relative_to(output))
                measured['artifacts'] = [a for a in measured['artifacts'] if a['role'] != 'mask']
                record['stages'][stage] = measured
                if measured['status'] != 'success':
                    record['processing_exclusions'] = [dict(error, stage=stage) for error in measured['errors']]
                    break
            else:
                record['scoring_eligible'] = True
    except Exception as exc:
        record['processing_exclusions'].append({'code': str(exc) if isinstance(exc, ValueError) else 'source_validation_failed',
            'message': 'Source identifier/series/privacy validation failed' if isinstance(exc, ValueError) else type(exc).__name__, 'stage': 'inventory'})
    return record


def prepare_collection(manifest, clinical_path, output_dir, *, workers=4, seed=42):
    """Validate full acquisition, measure patients, save immutable model inputs and split.

    Manifest entries explicitly identify all CT/RTSTRUCT series and files; an incomplete
    acquisition aborts rather than turning unfinished downloads into clinical exclusions.
    Existing completed outputs are replayed only with identical source/config inputs.
    """
    import csv
    import importlib.metadata
    import os
    from pathlib import Path
    from concurrent.futures import ProcessPoolExecutor
    from .config import PYRADIOMICS_CONFIG
    output = Path(output_dir).resolve()
    if not 1 <= workers <= 4:
        raise ValueError('Use between one and four bounded workers')
    grouped, source_identity = {}, []
    for entry in sorted(manifest, key=lambda e: (e['patient_id'], e['modality'], e['series_uid'])):
        if entry['modality'] not in ('CT', 'RTSTRUCT'):
            raise ValueError('Unsupported manifest modality')
        if len(entry['files']) != entry['expected_instances'] or not entry['files']:
            raise ValueError('Acquisition incomplete: expected instance count differs')
        for filename in sorted(entry['files']):
            path = Path(filename)
            if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
                raise ValueError('Acquisition incomplete or unsafe source file')
            source_identity.append((str(path.resolve()), path.stat().st_size, path.stat().st_mtime_ns))
        grouped.setdefault(entry['patient_id'], []).append(entry)
    if not grouped:
        raise ValueError('Empty collection manifest')
    versions = {name: importlib.metadata.version(name) for name in
                ('numpy', 'pydicom', 'SimpleITK', 'pyradiomics', 'rt-utils')}
    code = {name: _sha(Path(__file__).parent / name) for name in
            ('preparation.py', 'engine.py', 'dicom_loader.py', 'masks.py', 'extract_features.py', 'qc.py')}
    provenance = {'schema_version': 1, 'collection': 'public de-identified NSCLC-Radiomics / Lung1',
        'clinical_sha256': _sha(clinical_path), 'radiomics_config_sha256': _sha(PYRADIOMICS_CONFIG),
        'radiomics_configuration': PYRADIOMICS_CONFIG.read_text(), 'dependencies': versions,
        'engine_source_sha256': code, 'seed': seed, 'workers': workers,
        'source_identity_sha256': hashlib.sha256(json.dumps(source_identity).encode()).hexdigest(),
        'manifest_sha256': hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
        'learned_preprocessing': 'none; no feature filtering, scaling, model fitting or tuning',
        'series_policy': 'exactly one CT and one RTSTRUCT per patient; reject ambiguity; GTV-1 ROI; all referenced geometry validated by verified engine',
        'outcome_policy': 'unique exact patient join; duration finite >0 days; event in {0,1}; missing/invalid outcomes do not prevent scoring'}
    output.mkdir(parents=True, exist_ok=True)
    provenance_path = output / 'provenance.json'
    if provenance_path.exists() and json.loads(provenance_path.read_text()) != provenance:
        raise ValueError('Preparation inputs changed; use a new versioned output directory')
    _json(provenance_path, provenance)
    if (output / 'report.json').exists():
        return json.loads((output / 'report.json').read_text())
    _json(output / 'source_manifest.json', manifest)
    outcomes = _outcomes(clinical_path)
    clinical_only = sorted(set(outcomes) - set(grouped))
    jobs = [(patient, entries, str(output), outcomes.get(patient, (None,
        [{'code': 'missing_outcome', 'message': 'No clinical outcome row'}]))) for patient, entries in sorted(grouped.items())]
    records = []
    pending = []
    checkpoints = output / 'patients'
    checkpoints.mkdir(exist_ok=True)
    for job in jobs:
        checkpoint = checkpoints / f'{job[0]}.json'
        if checkpoint.exists():
            records.append(json.loads(checkpoint.read_text()))
        else:
            pending.append(job)
    # Bound BLAS/OpenMP in spawned workers as well as ITK's own runtime pool.
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'):
        os.environ[key] = '1'
    if workers == 1:
        measured = map(_prepare_patient, pending)
        for record in measured:
            records.append(record)
            _json(checkpoints / f"{record['patient_id']}.json", record)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for record in pool.map(_prepare_patient, pending, chunksize=1):
                records.append(record)
                _json(checkpoints / f"{record['patient_id']}.json", record)
                print(f"Prepared {len(records)}/{len(jobs)}: {record['patient_id']} eligible={record['scoring_eligible']}", flush=True)
    records.sort(key=lambda r: r['patient_id'])
    schemas = {tuple(r['stages']['features']['feature_schema']) for r in records if r['scoring_eligible']}
    if len(schemas) != 1:
        raise ValueError('No usable features or inconsistent measured feature schemas')
    schema = list(next(iter(schemas)))
    partition = freeze_partition(records, seed=seed)
    _json(output / 'partition.json', partition)
    _json(output / 'feature_schema.json', schema)
    with (output / 'features.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['patient_id', *schema])
        writer.writeheader()
        for r in records:
            if r['scoring_eligible']:
                writer.writerow({'patient_id': r['patient_id'], **r['stages']['features']['values']})
    with (output / 'outcomes.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['patient_id', 'duration', 'event', 'time_unit'])
        writer.writeheader()
        for r in records:
            if r['outcome']:
                writer.writerow({'patient_id': r['patient_id'], **r['outcome']})
    eligible = [r for r in records if r['scoring_eligible']]
    evaluation = [r for r in eligible if r['outcome']]
    report = {'schema_version': 1, 'counts': {'inventoried': len(records), 'scoring_eligible': len(eligible),
        'processing_excluded': len(records) - len(eligible), 'evaluation_eligible': len(evaluation),
        'evaluation_excluded': len(eligible) - len(evaluation), 'development': len(partition['development']),
        'held_out': len(partition['held_out'])}, 'clinical_only_ids': clinical_only, 'patients': records}
    _json(output / 'report.json', report)
    _json(output / 'catalog.json', {'schema_version': 1, 'partition_sha256': _sha(output / 'partition.json'),
        'patients': [{'id': p, 'label': 'Public Lung1 · frozen held-out patient', 'fixture': False} for p in partition['held_out']]})
    return report
