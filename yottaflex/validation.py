from .db import get_connection


def run_validation(database_path=None):
    conn = get_connection(database_path)
    report = {
        'total_records_checked': 0,
        'passed_validations': 0,
        'failed_validations': 0,
        'errors': [],
        'warnings': [],
        'referential_integrity_score': 100.0,
        'duplicate_count': 0,
        'invalid_relationship_count': 0,
    }
    tables = ['asset', 'instrument_type', 'calibration_plan', 'instrument', 'calibration_event', 'certificate', 'work_order', 'production_use', 'alert', 'audit_record', 'anomaly_issue', 'impact_assessment', 'exception_record']
    for table in tables:
        rows = conn.execute(f'SELECT * FROM {table}').fetchall()
        report['total_records_checked'] += len(rows)
    for row in conn.execute('SELECT instrument_id, asset_id FROM instrument WHERE asset_id NOT IN (SELECT asset_id FROM asset)').fetchall():
        report['failed_validations'] += 1
        report['errors'].append(f'Instrument {row[0]} points to missing asset {row[1]}')
    for row in conn.execute('SELECT certificate_id, instrument_id FROM certificate WHERE instrument_id NOT IN (SELECT instrument_id FROM instrument)').fetchall():
        report['failed_validations'] += 1
        report['errors'].append(f'Certificate {row[0]} points to missing instrument {row[1]}')
    for row in conn.execute('SELECT calibration_id, instrument_id FROM calibration_event WHERE instrument_id NOT IN (SELECT instrument_id FROM instrument)').fetchall():
        report['failed_validations'] += 1
        report['errors'].append(f'Calibration {row[0]} points to missing instrument {row[1]}')
    duplicate_count = 0
    for table in ['asset', 'instrument_type', 'supplier', 'instrument', 'calibration_event', 'certificate', 'work_order', 'production_use', 'alert', 'audit_record', 'anomaly_issue']:
        try:
            cols = conn.execute(f'PRAGMA table_info({table})').fetchall()
        except Exception:
            continue
        unique_cols = [c[1] for c in cols if c[1].endswith('_id') or c[1] == 'asset_id']
        for col in unique_cols:
            duplicate_count += len(conn.execute(f'SELECT {col} FROM {table} GROUP BY {col} HAVING COUNT(*) > 1').fetchall())
    report['duplicate_count'] = duplicate_count
    report['passed_validations'] = max(report['total_records_checked'] - report['failed_validations'], 0)
    if report['failed_validations']:
        report['referential_integrity_score'] = round(max(0.0, 100.0 - (report['failed_validations'] * 5.0)), 2)
    conn.close()
    return report
