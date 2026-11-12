import argparse
import json
import os

from yottaflex import create_app, generate_dataset, run_validation, reproducibility_report

app = create_app()


def _cli():
    parser = argparse.ArgumentParser(description='YottaFlex industrial calibration platform')
    parser.add_argument('--generate', choices=['starter', 'full'], help='Generate dataset')
    parser.add_argument('--validate', action='store_true', help='Run validation report')
    parser.add_argument('--reproducibility', action='store_true', help='Run reproducibility test')
    parser.add_argument('--reset', action='store_true', help='Reset the database')
    parser.add_argument('--seed', type=int, default=20261022, help='Random seed')
    args = parser.parse_args()

    db_path = app.config['DATABASE_PATH']
    if args.reset:
        if os.path.exists(db_path):
            os.remove(db_path)
        print(f'Removed database: {db_path}')
    if args.generate:
        report = generate_dataset(args.generate, seed=args.seed)
        print(json.dumps(report, indent=2))
    if args.validate:
        report = run_validation(db_path)
        print(json.dumps(report, indent=2))
    if args.reproducibility:
        print(json.dumps(reproducibility_report(), indent=2))
    if not any([args.generate, args.validate, args.reproducibility, args.reset]):
        app.run(debug=True, host='0.0.0.0', port=int(app.config.get('PORT', 5000)))


if __name__ == '__main__':
    _cli()
