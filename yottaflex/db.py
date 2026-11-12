import os
import sqlite3

from .config import BASE_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS asset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    site TEXT NOT NULL,
    region TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS instrument_type (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    unit TEXT
);
CREATE TABLE IF NOT EXISTS supplier (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    contact_email TEXT,
    country TEXT
);
CREATE TABLE IF NOT EXISTS calibration_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT UNIQUE NOT NULL,
    instrument_type_id INTEGER NOT NULL,
    interval_months INTEGER NOT NULL,
    tolerance_limit REAL NOT NULL,
    reference_standard TEXT,
    FOREIGN KEY (instrument_type_id) REFERENCES instrument_type(id)
);
CREATE TABLE IF NOT EXISTS instrument (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id TEXT UNIQUE NOT NULL,
    asset_id TEXT NOT NULL,
    instrument_type_id INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL,
    calibration_plan_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    manufacturer TEXT,
    model TEXT,
    serial_number TEXT,
    installation_date TEXT NOT NULL,
    last_calibration_date TEXT,
    next_due_date TEXT,
    status TEXT NOT NULL DEFAULT 'valid',
    location TEXT,
    criticality TEXT,
    assigned_supplier TEXT,
    FOREIGN KEY (asset_id) REFERENCES asset(asset_id),
    FOREIGN KEY (instrument_type_id) REFERENCES instrument_type(id),
    FOREIGN KEY (supplier_id) REFERENCES supplier(id),
    FOREIGN KEY (calibration_plan_id) REFERENCES calibration_plan(id)
);
CREATE TABLE IF NOT EXISTS calibration_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calibration_id TEXT UNIQUE NOT NULL,
    instrument_id TEXT NOT NULL,
    calibration_date TEXT NOT NULL,
    technician TEXT NOT NULL,
    supplier TEXT NOT NULL,
    measured_value REAL,
    reference_value REAL,
    tolerance_limit REAL,
    deviation REAL,
    pass_fail TEXT NOT NULL,
    certificate_reference TEXT,
    calibration_status TEXT NOT NULL,
    remarks TEXT,
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE TABLE IF NOT EXISTS certificate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    certificate_id TEXT UNIQUE NOT NULL,
    calibration_event_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    issue_date TEXT NOT NULL,
    expiry_date TEXT NOT NULL,
    supplier TEXT NOT NULL,
    document_reference TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    FOREIGN KEY (calibration_event_id) REFERENCES calibration_event(calibration_id),
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id),
    FOREIGN KEY (asset_id) REFERENCES asset(asset_id)
);
CREATE TABLE IF NOT EXISTS work_order (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id TEXT UNIQUE NOT NULL,
    instrument_id TEXT NOT NULL,
    work_order_type TEXT NOT NULL,
    priority TEXT NOT NULL,
    assigned_technician TEXT,
    creation_date TEXT NOT NULL,
    scheduled_date TEXT,
    completion_date TEXT,
    downtime_duration INTEGER DEFAULT 0,
    work_order_status TEXT NOT NULL,
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE TABLE IF NOT EXISTS production_use (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usage_id TEXT UNIQUE NOT NULL,
    instrument_id TEXT NOT NULL,
    production_line TEXT NOT NULL,
    usage_timestamp TEXT NOT NULL,
    operator_name TEXT NOT NULL,
    usage_duration INTEGER NOT NULL,
    calibration_valid_at_usage TEXT NOT NULL,
    usage_permission TEXT NOT NULL,
    exception_reference TEXT,
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE TABLE IF NOT EXISTS alert (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT UNIQUE NOT NULL,
    alert_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    acknowledged BOOLEAN DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    previous_state TEXT,
    new_state TEXT,
    user_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS anomaly_issue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id TEXT UNIQUE NOT NULL,
    issue_type TEXT NOT NULL,
    related_entity_id TEXT NOT NULL,
    description TEXT NOT NULL,
    detection_status TEXT NOT NULL,
    severity TEXT NOT NULL,
    ground_truth_label TEXT NOT NULL,
    expected_decision TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS impact_assessment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id TEXT UNIQUE NOT NULL,
    calibration_event_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id),
    FOREIGN KEY (calibration_event_id) REFERENCES calibration_event(calibration_id)
);
CREATE TABLE IF NOT EXISTS exception_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exception_id TEXT UNIQUE NOT NULL,
    instrument_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_instrument_asset_id ON instrument(asset_id);
CREATE INDEX IF NOT EXISTS idx_calibration_date ON calibration_event(calibration_date);
CREATE INDEX IF NOT EXISTS idx_certificate_instrument ON certificate(instrument_id);
CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON production_use(usage_timestamp);
CREATE INDEX IF NOT EXISTS idx_alert_severity ON alert(severity);
"""


def get_connection(database_path=None):
    path = database_path or os.getenv('DATABASE_PATH')
    if not path:
        os.makedirs(str(BASE_DIR / 'data'), exist_ok=True)
        path = str(BASE_DIR / 'data' / 'yottaflex.db')
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(database_path=None):
    conn = get_connection(database_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def reset_db(database_path=None):
    conn = get_connection(database_path)
    for table in [
        'audit_record', 'alert', 'production_use', 'work_order', 'certificate',
        'calibration_event', 'instrument', 'calibration_plan', 'instrument_type',
        'supplier', 'asset', 'exception_record', 'impact_assessment', 'anomaly_issue'
    ]:
        try:
            conn.execute(f'DROP TABLE IF EXISTS {table}')
        except Exception:
            pass
    conn.commit()
    conn.close()
    init_db(database_path)
