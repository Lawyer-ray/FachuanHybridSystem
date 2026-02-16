from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportFinding:
    file_path: str
    line_no: int
    imported_app: str
    import_stmt: str
    kind: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _backend_root() -> Path:
    return _repo_root() / "backend"


def _iter_python_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for p in root.rglob("*.py"):
        if "__pycache__" in str(p):
            continue
        paths.append(p)
    return paths


def _extract_cross_app_imports(file_path: Path, *, kind: str, module_suffix: str) -> list[ImportFinding]:
    findings: list[ImportFinding] = []
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        lines = content.splitlines()
    except (SyntaxError, UnicodeDecodeError):
        return []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module:
            continue
        if module_suffix not in node.module:
            continue
        match = re.match(rf"apps\.(\w+)\.{re.escape(module_suffix.lstrip('.'))}", node.module)
        if not match:
            continue
        imported_app = match.group(1)
        line_no = getattr(node, "lineno", 0) or 0
        import_stmt = lines[line_no - 1].strip() if 0 < line_no <= len(lines) else node.module
        findings.append(
            ImportFinding(
                file_path=str(file_path),
                line_no=line_no,
                imported_app=imported_app,
                import_stmt=import_stmt,
                kind=kind,
            )
        )
    return findings


def _audit_services_cross_app_model_imports() -> list[ImportFinding]:
    backend = _backend_root()
    services_root = backend / "apps"
    files = _iter_python_files(services_root)
    findings: list[ImportFinding] = []
    for f in files:
        if "/services/" not in str(f).replace("\\", "/"):
            continue
        findings.extend(_extract_cross_app_imports(f, kind="services_models", module_suffix=".models"))
    return findings


def _audit_tasks_cross_app_imports() -> list[ImportFinding]:
    backend = _backend_root()
    apps_root = backend / "apps"
    files = _iter_python_files(apps_root)
    findings: list[ImportFinding] = []
    for f in files:
        rel = str(f).replace("\\", "/")
        if "/tasks/" in rel or rel.endswith("/tasks.py") or "/tasks_" in rel or rel.endswith("_tasks.py"):
            findings.extend(_extract_cross_app_imports(f, kind="tasks_models", module_suffix=".models"))
            findings.extend(_extract_cross_app_imports(f, kind="tasks_services", module_suffix=".services"))
    return findings


def main() -> int:
    findings = []
    findings.extend(_audit_services_cross_app_model_imports())
    findings.extend(_audit_tasks_cross_app_imports())
    by_imported: dict[str, int] = {}
    by_file: dict[str, int] = {}

    for item in findings:
        by_imported_key = f"{item.kind}:{item.imported_app}"
        by_imported[by_imported_key] = by_imported.get(by_imported_key, 0) + 1
        by_file[item.file_path] = by_file.get(item.file_path, 0) + 1

    top_imported = sorted(by_imported.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    top_files = sorted(by_file.items(), key=lambda kv: (-kv[1], kv[0]))[:20]

    print("Cross-app imports inside services/ and tasks/")
    print(f"total_findings={len(findings)} unique_files={len(by_file)}")
    print("")

    print("Top imported targets:")
    for key, count in top_imported:
        print(f"- {key}: {count}")
    print("")

    print("Top files:")
    for path, count in top_files:
        print(f"- {path}: {count}")
    print("")

    print("First 50 findings:")
    for item in findings[:50]:
        print(f"- {item.file_path}:{item.line_no} {item.import_stmt}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
