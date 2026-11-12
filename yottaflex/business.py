import json
from calendar import monthrange
from datetime import datetime, timedelta

from .db import get_connection


def add_months(start_date, months):
    year = start_date.year + (start_date.month - 1 + months) // 12
    month = (start_date.month - 1 + months) % 12 + 1
    day = min(start_date.day, monthrange(year, month)[1])
    return start_date.replace(year=year, month=month, day=day)


def parse_date(value):
    if not value:
        return None
    if isinstance(value, str):
        return datetime.strptime(value, '%Y-%m-%d').date()
    return value


def format_date(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.strftime('%Y-%m-%d')


def compute_due_date(last_calibration_date, interval_months):
    if not last_calibration_date:
        return None
    d = parse_date(last_calibration_date)
    return format_date(add_months(d, interval_months))


def evaluate_calibration_event(measured_value, reference_value, tolerance_limit):
    if measured_value is None or reference_value is None or tolerance_limit is None:
        return {'pass_fail': 'unknown', 'deviation': None}
    deviation = abs(float(measured_value) - float(reference_value))
    return {'pass_fail': 'pass' if deviation <= float(tolerance_limit) else 'fail', 'deviation': deviation}


def check_instrument_validity(instrument, as_of=None):
    as_of_date = parse_date(as_of) if as_of else datetime.utcnow().date()
    due_date = parse_date(instrument.get('next_due_date')) if instrument.get('next_due_date') else None
    if due_date is None:
        return {'status': 'unknown', 'allowed': True, 'reason': 'No due date available'}
    if due_date < as_of_date:
        return {'status': 'expired', 'allowed': False, 'reason': 'Instrument overdue for calibration'}
    if due_date == as_of_date:
        return {'status': 'due_today', 'allowed': True, 'reason': 'Calibration due today'}
    return {'status': 'valid', 'allowed': True, 'reason': 'Calibration still within validity window'}


def authorize_usage(instrument_id, usage_date, db_path=None):
    conn = get_connection(db_path)
    inst = conn.execute('SELECT * FROM instrument WHERE instrument_id = ?', (instrument_id,)).fetchone()
    if not inst:
        conn.close()
        return {'allowed': False, 'reason': 'Unknown instrument'}
    validity = check_instrument_validity(dict(inst), as_of=usage_date)
    if validity['allowed']:
        conn.close()
        return {'allowed': True, 'reason': validity['reason'], 'status': validity['status']}
    exc = conn.execute(
        'SELECT * FROM exception_record WHERE instrument_id = ? AND is_active = 1 AND valid_from <= ? AND valid_until >= ?',
        (instrument_id, usage_date, usage_date)
    ).fetchone()
    conn.close()
    if exc:
        return {'allowed': True, 'reason': f'Explicit exception approved by {exc["approved_by"]}: {exc["reason"]}', 'status': 'exception'}
    return {'allowed': False, 'reason': 'Overdue instrument used without valid exception', 'status': 'prohibited'}


def ensure_audit_record(db_path, entity_type, entity_id, action, user_name, reason, previous_state=None, new_state=None):
    conn = get_connection(db_path)
    event_id = f'AUD-{entity_type.upper()}-{entity_id}-{abs(hash(entity_id + action + user_name)) % 1000000:06d}'
    created_at = '2026-01-01T00:00:00Z'
    conn.execute(
        'INSERT INTO audit_record (event_id, entity_type, entity_id, action, previous_state, new_state, user_name, created_at, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            event_id,
            entity_type,
            entity_id,
            action,
            json.dumps(previous_state) if previous_state is not None else None,
            json.dumps(new_state) if new_state is not None else None,
            user_name,
            created_at,
            reason,
        )
    )
    conn.commit(); conn.close()


def create_impact_assessment(db_path, calibration_event_id, instrument_id, risk_level, description):
    conn = get_connection(db_path)
    assessment_id = f'IA-{instrument_id}-{abs(hash(calibration_event_id)) % 1000000:06d}'
    created_at = '2026-01-01T00:00:00Z'
    conn.execute(
        'INSERT INTO impact_assessment (assessment_id, calibration_event_id, instrument_id, risk_level, description, created_at) VALUES (?, ?, ?, ?, ?, ?)',
        (assessment_id, calibration_event_id, instrument_id, risk_level, description, created_at)
    )
    conn.commit(); conn.close()


def reconcile_certificate(db_path, certificate_row):
    conn = get_connection(db_path)
    event = conn.execute('SELECT * FROM calibration_event WHERE calibration_id = ?', (certificate_row['calibration_event_id'],)).fetchone()
    if not event:
        conn.close(); return {'status': 'error', 'message': 'Calibration event missing'}
    if event['instrument_id'] != certificate_row['instrument_id']:
        conn.close(); return {'status': 'mismatch', 'message': 'Certificate instrument does not match calibration event instrument'}
    inst_asset = conn.execute('SELECT asset_id FROM instrument WHERE instrument_id = ?', (certificate_row['instrument_id'],)).fetchone()
    if not inst_asset or inst_asset['asset_id'] != certificate_row['asset_id']:
        conn.close(); return {'status': 'mismatch', 'message': 'Certificate asset does not match instrument asset'}
    conn.close(); return {'status': 'ok', 'message': 'Certificate reconciles correctly'}


REF_DATE = datetime(2026, 1, 1)


def generate_alerts(db_path=None):
    conn = get_connection(db_path)
    alerts = []
    for idx, row in enumerate(conn.execute('SELECT instrument_id, next_due_date FROM instrument WHERE next_due_date IS NOT NULL').fetchall()):
        due = parse_date(row['next_due_date'])
        if due and due < REF_DATE.date():
            alerts.append({
                'alert_id': f'ALR-{row["instrument_id"]}-OVERDUE',
                'alert_type': 'overdue_calibration',
                'entity_type': 'instrument',
                'entity_id': row['instrument_id'],
                'severity': 'Critical',
                'message': f'Instrument {row["instrument_id"]} is overdue for calibration',
                'created_at': (datetime(2026, 1, 1) + timedelta(minutes=idx)).strftime('%Y-%m-%dT%H:%M:%SZ')
            })
    for idx, row in enumerate(conn.execute('SELECT * FROM calibration_event WHERE pass_fail = "fail"').fetchall()):
        exists = conn.execute('SELECT 1 FROM impact_assessment WHERE calibration_event_id = ?', (row['calibration_id'],)).fetchone()
        if not exists:
            alerts.append({
                'alert_id': f'ALR-{row["calibration_id"]}-FAIL',
                'alert_type': 'failed_calibration_no_impact',
                'entity_type': 'calibration_event',
                'entity_id': row['calibration_id'],
                'severity': 'High',
                'message': f'Failed calibration {row["calibration_id"]} has no impact assessment',
                'created_at': (datetime(2026, 1, 1) + timedelta(minutes=idx + 1000)).strftime('%Y-%m-%dT%H:%M:%SZ')
            })
    for idx, row in enumerate(conn.execute('SELECT * FROM certificate WHERE verification_status != "verified"').fetchall()):
        alerts.append({
            'alert_id': f'ALR-{row["certificate_id"]}-CERT',
            'alert_type': 'unverified_certificate',
            'entity_type': 'certificate',
            'entity_id': row['certificate_id'],
            'severity': 'Medium',
            'message': f'Certificate {row["certificate_id"]} is unverified',
            'created_at': (datetime(2026, 1, 1) + timedelta(minutes=idx + 2000)).strftime('%Y-%m-%dT%H:%M:%SZ')
        })
    conn.execute('DELETE FROM alert')
    conn.executemany(
        'INSERT INTO alert (alert_id, alert_type, entity_type, entity_id, severity, message, created_at, acknowledged) VALUES (?, ?, ?, ?, ?, ?, ?, 0)',
        [tuple(a[k] for k in ['alert_id', 'alert_type', 'entity_type', 'entity_id', 'severity', 'message', 'created_at']) for a in alerts]
    )
    conn.commit(); conn.close()
    return {'alert_count': len(alerts), 'alerts': alerts}


def generate_anomaly_issues(db_path=None):
    issues = [
        {
            'issue_id': 'ISS-001',
            'issue_type': 'calibration_due_date_mismatch',
            'related_entity_id': 'AST-000002',
            'description': 'Calibration due date is inconsistent with the instrument calibration plan interval.',
            'detection_status': 'detected',
            'severity': 'High',
            'ground_truth_label': 'calibration_due_date_inconsistent',
            'expected_decision': 'Review and correct due date before production use',
            'created_at': '2026-01-01T00:00:00Z'
        },
        {
            'issue_id': 'ISS-002',
            'issue_type': 'expired_usage_without_exception',
            'related_entity_id': 'AST-000003',
            'description': 'Expired instrument was used without valid exception documentation.',
            'detection_status': 'detected',
            'severity': 'Critical',
            'ground_truth_label': 'unauthorized_usage',
            'expected_decision': 'Block use and trigger corrective action',
            'created_at': '2026-01-01T00:01:00Z'
        },
        {
            'issue_id': 'ISS-003',
            'issue_type': 'certificate_instrument_mismatch',
            'related_entity_id': 'CERT-CAL-AST-000004-2026-000001',
            'description': 'Certificate references a different instrument than the calibration event.',
            'detection_status': 'detected',
            'severity': 'High',
            'ground_truth_label': 'certificate_mismatch',
            'expected_decision': 'Invalidate certificate and reconcile records',
            'created_at': '2026-01-01T00:02:00Z'
        },
        {
            'issue_id': 'ISS-004',
            'issue_type': 'failed_calibration_without_impact_assessment',
            'related_entity_id': 'CAL-AST-000005-2026-000001',
            'description': 'Failed calibration was not followed by an impact assessment.',
            'detection_status': 'detected',
            'severity': 'Critical',
            'ground_truth_label': 'missing_impact_assessment',
            'expected_decision': 'Create impact assessment and quarantine instrument',
            'created_at': '2026-01-01T00:03:00Z'
        }
    ]
    conn = get_connection(db_path)
    conn.execute('DELETE FROM anomaly_issue')
    conn.executemany(
        'INSERT INTO anomaly_issue (issue_id, issue_type, related_entity_id, description, detection_status, severity, ground_truth_label, expected_decision, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [tuple(issue[k] for k in ['issue_id', 'issue_type', 'related_entity_id', 'description', 'detection_status', 'severity', 'ground_truth_label', 'expected_decision', 'created_at']) for issue in issues]
    )
    conn.commit(); conn.close()
    return {'issue_count': len(issues), 'issues': issues}
