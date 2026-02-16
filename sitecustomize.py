import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"
APISYSTEM_DIR = BACKEND_DIR / "apiSystem"

for p in (str(BACKEND_DIR), str(APISYSTEM_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
os.environ.setdefault("DJANGO_DEBUG", "1")
os.environ.setdefault("DATABASE_PATH", "/tmp/fachuan_pytest.sqlite3")
