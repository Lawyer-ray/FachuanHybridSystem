from pathlib import Path


def test_no_zipfile_extractall_in_apps():
    backend_root = Path(__file__).parent.parent.parent
    apps_dir = backend_root / "apps"
    bad = []
    for py in apps_dir.rglob("*.py"):
        if "migrations" in py.parts:
            continue
        text = py.read_text(encoding="utf-8")
        if ".extractall(" in text:
            bad.append(str(py))
    assert not bad
