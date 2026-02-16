import os
import re

import pytest
from apps.core.path import Path


@pytest.mark.property_test
def test_api_layer_no_direct_io_task_or_db_writes():
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"

    allow_open = {
        "apps/automation/api/auto_namer_api.py",
        "apps/automation/api/court_document_recognition_api.py",
        "apps/automation/api/fee_notice_extraction_api.py",
        "apps/automation/api/preservation_date_extraction_api.py",
        "apps/automation/services/document_delivery/api/document_delivery_api_service.py",
    }
    allow_async_task = {
        "apps/automation/api/court_document_recognition_api.py",
    }
    allow_db_writes = {
        "apps/automation/api/court_document_recognition_api.py",
        "apps/automation/services/document_delivery/api/document_delivery_api_service.py",
    }

    errors = []

    api_files = []
    for py_file in apps_path.glob("**/api/**/*.py"):
        if py_file.name == "__init__.py":
            continue
        api_files.append(py_file)

    for file_path in api_files:
        rel = os.path.relpath(str(file_path), str(backend_path))
        content = file_path.read_text()

        if ("from django_q.tasks import async_task" in content) or re.search(r"\basync_task\s*\(", content):
            if rel not in allow_async_task:
                errors.append(f"{rel}: API 层禁止直接 async_task(...)，请下沉到 facade/usecase")

        if re.search(r"(?<!\.)\bopen\s*\(", content):
            if rel not in allow_open:
                errors.append(f"{rel}: API 层禁止直接 open(...)，请下沉到 IO 组件/服务")

        db_write_patterns = [
            r"\.objects\.create\s*\(",
            r"\.objects\.bulk_create\s*\(",
            r"\.objects\.update\s*\(",
            r"\.objects\.[a-zA-Z_]+\([^)]*\)\.update\s*\(",
            r"\.objects\.delete\s*\(",
        ]
        if any(re.search(p, content, flags=re.DOTALL) for p in db_write_patterns):
            if rel not in allow_db_writes:
                errors.append(f"{rel}: API 层禁止直接 ORM 写入（create/update/delete），请下沉到 service/facade")

    assert not errors, "API 合规性守护失败：\n" + "\n".join(f"- {e}" for e in errors)
