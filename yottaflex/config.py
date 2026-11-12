import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = os.getenv('DATABASE_PATH', str(BASE_DIR / 'data' / 'yottaflex.db'))


class Config:
    DATABASE_PATH = DEFAULT_DB
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret')
    PORT = int(os.getenv('PORT', '5000'))
