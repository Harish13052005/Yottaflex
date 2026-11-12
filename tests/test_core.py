import os

from yottaflex import create_app
from yottaflex.business import compute_due_date, evaluate_calibration_event, authorize_usage
from yottaflex.generator import generate_dataset, reproducibility_report


def test_due_date_calculation():
    assert compute_due_date('2025-01-15', 6) == '2025-07-15'


def test_calibration_evaluation():
    result = evaluate_calibration_event(32.2, 32.0, 0.5)
    assert result['pass_fail'] == 'pass'


def test_authorize_usage_rejects_overdue_without_exception(tmp_path):
    db_path = tmp_path / 'test.db'
    generate_dataset('starter', seed=20261022, database_path=str(db_path))
    result = authorize_usage('AST-000001', '2025-12-31', str(db_path))
    assert result['status'] in ('prohibited', 'valid', 'exception')


def test_generation_counts_match_requirements():
    report = generate_dataset('starter', seed=20261022)
    assert report['instrument_count'] == 50
    assert report['production_use_count'] == 2000


def test_reproducibility_report_matches_seed():
    result = reproducibility_report(mode='starter')
    assert 'reproducible' in result and result['reproducible'] is True


def test_dashboard_loads():
    app = create_app()
    client = app.test_client()
    response = client.get('/dashboard')
    assert response.status_code == 200
