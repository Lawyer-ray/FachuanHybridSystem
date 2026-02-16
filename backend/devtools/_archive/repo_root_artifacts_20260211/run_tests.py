import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    backend_dir = repo_root / "backend"
    api_system_dir = backend_dir / "apiSystem"

    for p in (backend_dir, api_system_dir):
        sys.path.insert(0, str(p))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
    os.environ.setdefault("DJANGO_DEBUG", "1")
    os.environ.setdefault("DATABASE_PATH", "/tmp/fachuan_pytest.sqlite3")
    db_path = Path(os.environ["DATABASE_PATH"])
    if db_path.exists():
        db_path.unlink()

    import pytest

    args = sys.argv[1:] if len(sys.argv) > 1 else ["-q"]
    return pytest.main(["--ds=apiSystem.settings", *args])


if __name__ == "__main__":
    raise SystemExit(main())
