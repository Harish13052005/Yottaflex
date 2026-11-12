# YottaFlex.ai Industrial Calibration & Compliance Management Platform

This project delivers a production-oriented industrial calibration and compliance workspace for manufacturing plants.

## Features
- Instrument lifecycle management
- Calibration scheduling and pass/fail evaluation
- Certificate management and reconciliation
- Production-use authorization rules
- Alerts and anomaly tracking
- Synthetic, seed-driven dataset generation
- Dashboard and operational analytics

## Quick start

```bash
python -m venv .venv
. .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Open http://localhost:5000

## CLI commands

```bash
python main.py --generate starter
python main.py --generate full
python main.py --validate
python main.py --reproducibility
```
