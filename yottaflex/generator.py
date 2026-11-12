import hashlib
import json
import os
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .business import compute_due_date, evaluate_calibration_event, generate_alerts, generate_anomaly_issues, ensure_audit_record
from .db import get_connection, init_db

BASE_DIR = Path(__file__).resolve().parent.parent
SEED = 20261022
REFERENCE_DATE = datetime(2026, 1, 1, 0, 0, 0)


def _iso(dt):
    return dt.strftime('%Y-%m-%d')


def _iso_dt(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def generate_dataset(mode='starter', seed=SEED, database_path=None):
    db_path = database_path or str(BASE_DIR / 'data' / 'yottaflex.db')
    os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
    init_db(db_path)
    conn = get_connection(db_path)
    rng = random.Random(seed)

    if mode == 'starter':
        instrument_count = 50
        calibration_event_count = 140
        usage_count = 2000
    else:
        instrument_count = 2000
        calibration_event_count = 5000
        usage_count = 100000

    conn.execute('DELETE FROM production_use')
    conn.execute('DELETE FROM work_order')
    conn.execute('DELETE FROM certificate')
    conn.execute('DELETE FROM calibration_event')
    conn.execute('DELETE FROM instrument')
    conn.execute('DELETE FROM calibration_plan')
    conn.execute('DELETE FROM instrument_type')
    conn.execute('DELETE FROM supplier')
    conn.execute('DELETE FROM asset')
    conn.execute('DELETE FROM alert')
    conn.execute('DELETE FROM audit_record')
    conn.execute('DELETE FROM anomaly_issue')
    conn.execute('DELETE FROM impact_assessment')
    conn.execute('DELETE FROM exception_record')
    conn.commit()

    supplier_names = ['ApexMetrology', 'Nordic Precision', 'Atlas Instruments', 'Flowline QA', 'Kinetic Labs', 'Prime Calibration']
    supplier_rows = []
    for idx, name in enumerate(supplier_names, 1):
        supplier_rows.append((f'SUP-{idx:04d}', name, f'{name.lower().replace(" ", "")}@example.com', ['US', 'DE', 'IN', 'JP', 'FR'][idx % 5]))
    conn.executemany('INSERT INTO supplier (supplier_id, name, contact_email, country) VALUES (?, ?, ?, ?)', supplier_rows)

    asset_rows = []
    for idx in range(1, 250):
        asset_rows.append((f'ASSET-{idx:06d}', f'Line {idx}', 'Packaging', 'Plant A', 'North', _iso_dt(REFERENCE_DATE - timedelta(days=idx * 3))))
    conn.executemany('INSERT INTO asset (asset_id, name, category, site, region, created_at) VALUES (?, ?, ?, ?, ?, ?)', asset_rows)

    types = [
        ('PT100', 'Temperature Sensor', 'Temperature', 'C'),
        ('DP-200', 'Pressure Gauge', 'Pressure', 'psi'),
        ('FLOW-4', 'Flow Meter', 'Flow', 'L/min'),
        ('VIB-9', 'Vibration Sensor', 'Vibration', 'mm/s'),
        ('PH-7', 'pH Meter', 'Chemical', 'pH')
    ]
    conn.executemany('INSERT INTO instrument_type (type_code, name, description, unit) VALUES (?, ?, ?, ?)', types)

    calibration_plans = []
    for idx, (code, name, desc, unit) in enumerate(types, 1):
        interval = 6 if idx % 2 == 0 else 12
        tolerance = 0.5 if idx % 2 == 0 else 1.0
        calibration_plans.append((f'PLAN-{code}', idx, interval, tolerance, 'NIST Traceable'))
    conn.executemany('INSERT INTO calibration_plan (plan_id, instrument_type_id, interval_months, tolerance_limit, reference_standard) VALUES (?, ?, ?, ?, ?)', calibration_plans)

    instruments = []
    for i in range(1, instrument_count + 1):
        asset_id = f'ASSET-{((i - 1) % 249) + 1:06d}'
        type_idx = (i - 1) % len(types) + 1
        plan_id = conn.execute('SELECT id FROM calibration_plan WHERE instrument_type_id = ?', (type_idx,)).fetchone()[0]
        supplier_id = (i % 5) + 1
        inst_id = f'AST-{i:06d}'
        installation = datetime(2020, 1, 1) + timedelta(days=i % 365)
        last_cal = installation + timedelta(days=(i % 180))
        interval = conn.execute('SELECT interval_months FROM calibration_plan WHERE id = ?', (plan_id,)).fetchone()[0]
        next_due = compute_due_date(_iso(last_cal), interval)
        instruments.append((
            inst_id, asset_id, type_idx, supplier_id, plan_id, f'Instrument {i}', 'Acme', f'Model-{i % 17}', f'SN-{i:08d}',
            _iso(installation), _iso(last_cal), next_due, 'valid', f'Cell {((i - 1) % 12) + 1}', ['Low', 'Medium', 'High'][i % 3], f'SUP-{supplier_id:04d}'
        ))
    conn.executemany(
        'INSERT INTO instrument (instrument_id, asset_id, instrument_type_id, supplier_id, calibration_plan_id, name, manufacturer, model, serial_number, installation_date, last_calibration_date, next_due_date, status, location, criticality, assigned_supplier) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        instruments
    )

    event_rows = []
    for i in range(1, calibration_event_count + 1):
        instrument_id = f'AST-{((i - 1) % instrument_count) + 1:06d}'
        date = datetime(2025, 1, 1) + timedelta(days=i % 365)
        plan = conn.execute(
            'SELECT cp.interval_months, cp.tolerance_limit FROM calibration_plan cp JOIN instrument inst ON inst.calibration_plan_id = cp.id WHERE inst.instrument_id = ?',
            (instrument_id,)
        ).fetchone()
        if not plan:
            continue
        reference = 45 + ((i * 7) % 80)
        measured = reference + rng.uniform(-2.5, 2.5)
        result = evaluate_calibration_event(measured, reference, plan['tolerance_limit'])
        cal_id = f'CAL-{instrument_id}-{date.year}-{i:06d}'
        event_rows.append((cal_id, instrument_id, _iso(date), 'Tech-001', 'ApexMetrology', measured, reference, plan['tolerance_limit'], result['deviation'], result['pass_fail'], f'CERT-{cal_id}', result['pass_fail'], 'Nominal'))
    conn.executemany(
        'INSERT INTO calibration_event (calibration_id, instrument_id, calibration_date, technician, supplier, measured_value, reference_value, tolerance_limit, deviation, pass_fail, certificate_reference, calibration_status, remarks) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        event_rows
    )

    for row in event_rows:
        cert_id = f'CERT-{row[0]}'
        inst = conn.execute('SELECT instrument_id, asset_id FROM instrument WHERE instrument_id = ?', (row[1],)).fetchone()
        expiry = datetime.strptime(row[2], '%Y-%m-%d') + timedelta(days=365)
        verification = 'verified' if row[9] == 'pass' else 'unverified'
        conn.execute(
            'INSERT INTO certificate (certificate_id, calibration_event_id, instrument_id, asset_id, issue_date, expiry_date, supplier, document_reference, verification_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (cert_id, row[0], row[1], inst['asset_id'], row[2], _iso(expiry), row[4], f'file://cert/{cert_id}.pdf', verification)
        )

    for idx in range(1, usage_count + 1):
        inst_id = f'AST-{((idx - 1) % instrument_count) + 1:06d}'
        ts = datetime(2025, 1, 1) + timedelta(minutes=idx)
        inst = conn.execute('SELECT * FROM instrument WHERE instrument_id = ?', (inst_id,)).fetchone()
        allowed = True
        permission = 'authorized'
        if inst and inst['next_due_date'] and datetime.strptime(inst['next_due_date'], '%Y-%m-%d').date() < ts.date():
            allowed = False
            permission = 'prohibited'
        conn.execute(
            'INSERT INTO production_use (usage_id, instrument_id, production_line, usage_timestamp, operator_name, usage_duration, calibration_valid_at_usage, usage_permission, exception_reference) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (f'USE-{inst_id}-{ts.strftime("%Y%m%dT%H%M%S")}', inst_id, f'Line-{(idx % 12) + 1}', _iso_dt(ts), f'Operator-{(idx % 75) + 1:03d}', 30 + (idx % 120), 'valid' if allowed else 'expired', permission, None if allowed else 'EXC-0001')
        )

    for idx in range(1, 50):
        instrument_id = f'AST-{idx:06d}'
        if idx % 4 == 0:
            conn.execute(
                'INSERT INTO exception_record (exception_id, instrument_id, reason, approved_by, valid_from, valid_until, is_active) VALUES (?, ?, ?, ?, ?, ?, 1)',
                (f'EXC-{idx:04d}', instrument_id, 'Temporary calibration extension authorized for critical production', 'QA-Manager', '2025-03-01', '2025-03-31')
            )

    for idx in range(1, 30):
        inst_id = f'AST-{idx:06d}'
        if idx % 10 == 0:
            conn.execute(
                'INSERT INTO work_order (work_order_id, instrument_id, work_order_type, priority, assigned_technician, creation_date, scheduled_date, completion_date, downtime_duration, work_order_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (f'WO-2026-{idx:06d}', inst_id, 'Calibration', 'High', 'Technician A', '2026-01-01', '2026-01-05', '2026-01-06', 180, 'Completed')
            )

    for row in conn.execute('SELECT * FROM calibration_event WHERE pass_fail = "fail" ORDER BY calibration_date LIMIT 10').fetchall():
        conn.execute(
            'INSERT INTO impact_assessment (assessment_id, calibration_event_id, instrument_id, risk_level, description, created_at) VALUES (?, ?, ?, ?, ?, ?)',
            (f'IA-{row["instrument_id"]}-{row["calibration_id"]}', row['calibration_id'], row['instrument_id'], 'High', 'Failed calibration requires product impact review and containment.', _iso_dt(REFERENCE_DATE))
        )

    conn.commit()
    alert_summary = generate_alerts(db_path)
    generate_anomaly_issues(db_path)
    for row in conn.execute('SELECT * FROM instrument ORDER BY instrument_id').fetchall():
        ensure_audit_record(db_path, 'instrument', row['instrument_id'], 'generate', 'system', 'Synthetic record creation', previous_state=None, new_state={'status': row['status']})
    conn.close()
    return {
        'dataset': mode,
        'seed': seed,
        'instrument_count': instrument_count,
        'calibration_event_count': len(event_rows),
        'production_use_count': usage_count,
        'alert_count': alert_summary['alert_count'],
    }


def reproducibility_report(database_path=None, mode='starter'):
    db_path = database_path or str(BASE_DIR / 'data' / 'yottaflex.db')
    file_a = BASE_DIR / 'data' / 'repro_a.sqlite'
    file_b = BASE_DIR / 'data' / 'repro_b.sqlite'

    def remove_if_exists(path):
        for _ in range(20):
            try:
                if path.exists():
                    path.unlink()
                return
            except PermissionError:
                import time
                time.sleep(0.1)

    for path in [file_a, file_b]:
        remove_if_exists(path)

    generate_dataset(mode, seed=SEED, database_path=str(file_a))
    generate_dataset(mode, seed=SEED, database_path=str(file_b))

    def checksum(path):
        h = hashlib.sha256()
        conn = sqlite3.connect(path)
        for table_name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            rows = conn.execute(f'SELECT * FROM {table_name} ORDER BY 1').fetchall()
            h.update(table_name.encode())
            for row in rows:
                h.update(json.dumps(row, default=str).encode())
        conn.close()
        return h.hexdigest()

    sha_a = checksum(str(file_a))
    sha_b = checksum(str(file_b))
    return {'seed': SEED, 'mode': mode, 'reproducible': sha_a == sha_b, 'checksum_a': sha_a, 'checksum_b': sha_b}
