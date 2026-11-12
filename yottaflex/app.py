import os
from datetime import datetime

from flask import Flask, jsonify, render_template, request

from .business import authorize_usage, generate_alerts, reconcile_certificate
from .config import Config
from .db import get_connection, init_db
from .generator import generate_dataset, reproducibility_report
from .validation import run_validation


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
        static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'),
    )
    app.config.from_object(Config)
    os.makedirs(os.path.dirname(app.config['DATABASE_PATH']) or '.', exist_ok=True)
    init_db(app.config['DATABASE_PATH'])

    @app.route('/')
    def index():
        return dashboard()

    @app.route('/dashboard')
    def dashboard():
        conn = get_connection(app.config['DATABASE_PATH'])
        total_instruments = conn.execute('SELECT COUNT(*) FROM instrument').fetchone()[0]
        valid_instruments = conn.execute('SELECT COUNT(*) FROM instrument WHERE next_due_date >= date("now")').fetchone()[0]
        overdue_instruments = conn.execute('SELECT COUNT(*) FROM instrument WHERE next_due_date < date("now")').fetchone()[0]
        upcoming = conn.execute('SELECT COUNT(*) FROM instrument WHERE next_due_date BETWEEN date("now") AND date("now", "+30 days")').fetchone()[0]
        failed_calibrations = conn.execute('SELECT COUNT(*) FROM calibration_event WHERE pass_fail = "fail"').fetchone()[0]
        missing_certificates = conn.execute('SELECT COUNT(*) FROM instrument i LEFT JOIN certificate c ON c.instrument_id = i.instrument_id WHERE c.instrument_id IS NULL').fetchone()[0]
        unauthorized_usage = conn.execute('SELECT COUNT(*) FROM production_use WHERE usage_permission = "prohibited"').fetchone()[0]
        alerts = conn.execute('SELECT alert_type, severity, COUNT(*) AS c FROM alert GROUP BY alert_type, severity ORDER BY severity').fetchall()
        recent_activity = conn.execute('SELECT * FROM audit_record ORDER BY created_at DESC LIMIT 6').fetchall()
        conn.close()
        return render_template('dashboard.html', total_instruments=total_instruments, valid_instruments=valid_instruments, overdue_instruments=overdue_instruments, upcoming_calibrations=upcoming, failed_calibrations=failed_calibrations, missing_certificates=missing_certificates, unauthorized_usage=unauthorized_usage, alerts=alerts, recent_activity=recent_activity)

    @app.route('/instruments')
    def instruments():
        conn = get_connection(app.config['DATABASE_PATH'])
        rows = conn.execute('SELECT * FROM instrument ORDER BY instrument_id LIMIT 100').fetchall()
        conn.close()
        return render_template('instruments.html', instruments=rows)

    @app.route('/calibration')
    def calibration():
        conn = get_connection(app.config['DATABASE_PATH'])
        rows = conn.execute('SELECT * FROM calibration_event ORDER BY calibration_date DESC LIMIT 100').fetchall()
        conn.close()
        return render_template('calibration.html', events=rows)

    @app.route('/certificates')
    def certificates():
        conn = get_connection(app.config['DATABASE_PATH'])
        rows = conn.execute('SELECT * FROM certificate ORDER BY issue_date DESC LIMIT 100').fetchall()
        conn.close()
        return render_template('certificates.html', certificates=rows)

    @app.route('/work-orders')
    def work_orders():
        conn = get_connection(app.config['DATABASE_PATH'])
        rows = conn.execute('SELECT * FROM work_order ORDER BY creation_date DESC LIMIT 100').fetchall()
        conn.close()
        return render_template('work_orders.html', work_orders=rows)

    @app.route('/usage')
    def usage():
        conn = get_connection(app.config['DATABASE_PATH'])
        rows = conn.execute('SELECT * FROM production_use ORDER BY usage_timestamp DESC LIMIT 100').fetchall()
        conn.close()
        return render_template('usage.html', usage_rows=rows)

    @app.route('/alerts')
    def alerts():
        conn = get_connection(app.config['DATABASE_PATH'])
        rows = conn.execute('SELECT * FROM alert ORDER BY created_at DESC LIMIT 100').fetchall()
        conn.close()
        return render_template('alerts.html', alerts=rows)

    @app.route('/quality')
    def quality():
        report = run_validation(app.config['DATABASE_PATH'])
        return render_template('quality.html', report=report)

    @app.route('/audit')
    def audit():
        conn = get_connection(app.config['DATABASE_PATH'])
        rows = conn.execute('SELECT * FROM audit_record ORDER BY created_at DESC LIMIT 100').fetchall()
        conn.close()
        return render_template('audit.html', audits=rows)

    @app.route('/generator')
    def generator_page():
        return render_template('generator.html')

    @app.route('/settings')
    def settings():
        return render_template('settings.html')

    @app.route('/api/dashboard')
    def api_dashboard():
        conn = get_connection(app.config['DATABASE_PATH'])
        result = {
            'total_instruments': conn.execute('SELECT COUNT(*) FROM instrument').fetchone()[0],
            'overdue_instruments': conn.execute('SELECT COUNT(*) FROM instrument WHERE next_due_date < date("now")').fetchone()[0],
            'valid_instruments': conn.execute('SELECT COUNT(*) FROM instrument WHERE next_due_date >= date("now")').fetchone()[0],
            'upcoming_calibrations': conn.execute('SELECT COUNT(*) FROM instrument WHERE next_due_date BETWEEN date("now") AND date("now", "+30 days")').fetchone()[0],
            'failed_calibrations': conn.execute('SELECT COUNT(*) FROM calibration_event WHERE pass_fail = "fail"').fetchone()[0],
            'missing_certificates': conn.execute('SELECT COUNT(*) FROM instrument i LEFT JOIN certificate c ON c.instrument_id = i.instrument_id WHERE c.instrument_id IS NULL').fetchone()[0],
            'unauthorized_usage': conn.execute('SELECT COUNT(*) FROM production_use WHERE usage_permission = "prohibited"').fetchone()[0],
        }
        conn.close()
        return jsonify(result)

    @app.route('/api/generate', methods=['POST'])
    def api_generate():
        data = request.get_json(silent=True) or {}
        mode = data.get('mode', 'starter')
        seed = int(data.get('seed', 20261022))
        report = generate_dataset(mode, seed=seed, database_path=app.config['DATABASE_PATH'])
        return jsonify(report)

    @app.route('/api/validate', methods=['POST'])
    def api_validate():
        return jsonify(run_validation(app.config['DATABASE_PATH']))

    @app.route('/api/reproducibility', methods=['GET'])
    def api_reproducibility():
        return jsonify(reproducibility_report())

    @app.route('/api/usage/authorize', methods=['POST'])
    def api_usage_authorize():
        data = request.get_json(silent=True) or {}
        instrument_id = data.get('instrument_id')
        usage_date = data.get('usage_date') or datetime.utcnow().strftime('%Y-%m-%d')
        return jsonify(authorize_usage(instrument_id, usage_date, app.config['DATABASE_PATH']))

    @app.route('/api/certificate/reconcile', methods=['POST'])
    def api_reconcile_certificate():
        data = request.get_json(silent=True) or {}
        cert = data.get('certificate')
        return jsonify(reconcile_certificate(app.config['DATABASE_PATH'], cert))

    @app.route('/api/anomalies', methods=['GET'])
    def api_anomalies():
        conn = get_connection(app.config['DATABASE_PATH'])
        rows = conn.execute('SELECT * FROM anomaly_issue ORDER BY created_at DESC').fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/alerts', methods=['GET'])
    def api_alerts():
        generate_alerts(app.config['DATABASE_PATH'])
        conn = get_connection(app.config['DATABASE_PATH'])
        rows = conn.execute('SELECT * FROM alert ORDER BY created_at DESC').fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])

    return app


app = create_app()
