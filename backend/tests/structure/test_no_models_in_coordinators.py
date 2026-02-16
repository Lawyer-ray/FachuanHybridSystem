import re
from pathlib import Path


def test_coordinator_orchestrator_files_do_not_use_django_models_directly():
    root = Path(__file__).resolve().parents[2] / "apps"
    patterns = [
        "**/coordinator/**/*.py",
        "**/coordinators/**/*.py",
        "**/orchestrator/**/*.py",
        "**/orchestrators/**/*.py",
    ]

    model_import_re = re.compile(r"from\\s+apps\\.[a-zA-Z0-9_]+\\.models\\s+import\\s+")
    objects_re = re.compile(r"\\.objects\\b")

    violations = []
    for pattern in patterns:
        for file_path in root.glob(pattern):
            content = file_path.read_text(encoding="utf-8")
            if model_import_re.search(content) or objects_re.search(content):
                violations.append(str(file_path))

    assert not violations, "Coordinator/Orchestrator 不应直接操作 ORM: " + ", ".join(violations)
