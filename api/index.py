import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import init_db

init_db()

app.secret_key = os.environ.get('SECRET_KEY', 'hsa-minit-mesyuarat-2026-secret')
