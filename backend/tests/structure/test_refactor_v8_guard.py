from pathlib import Path


def test_refactor_targets_do_not_import_service_locator():
    root = Path(__file__).resolve().parents[2]
    targets = [
        root / "apps" / "automation" / "services" / "token" / "auto_login_service.py",
        root / "apps" / "automation" / "services" / "sms",
        root / "apps" / "documents" / "services" / "folder_service.py",
        root / "apps" / "documents" / "services" / "folder_template",
    ]

    paths: list[Path] = []
    for target in targets:
        assert target.exists(), f"missing: {target}"
        if target.is_dir():
            paths.extend(target.rglob("*.py"))
        else:
            paths.append(target)

    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert (
            "from apps.core.interfaces import ServiceLocator" not in content
        ), f"{path} should not import ServiceLocator"


def test_court_sms_stages_do_not_import_django_q_tasks():
    root = Path(__file__).resolve().parents[2]
    stage_dir = root / "apps" / "automation" / "services" / "sms" / "stages"
    assert stage_dir.exists(), f"missing: {stage_dir}"

    for path in stage_dir.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert "django_q.tasks" not in content, f"{path} should not import django_q.tasks"


def test_court_sms_helpers_do_not_import_django_q_tasks():
    root = Path(__file__).resolve().parents[2]
    path = root / "apps" / "automation" / "services" / "sms" / "court_sms_helpers.py"
    assert path.exists(), f"missing: {path}"
    content = path.read_text(encoding="utf-8")
    assert "django_q.tasks" not in content, f"{path} should not import django_q.tasks"
