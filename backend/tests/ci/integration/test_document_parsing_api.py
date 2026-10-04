"""Document Parsing API integration tests.

覆盖 /api/v1/document-parsing 的三个 GET 端点（records 列表 / records 详情 /
task 状态轮询）的归属过滤与响应结构契约——前端 material-prep 的解析历史
弹窗与轮询依赖这些端点（frontend/src/features/material-prep/api/document-parsing.ts）。
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from apps.document_parsing.models import DocumentParsingTask
from apps.organization.models import LawFirm, Lawyer


def _make_user(username: str, *, superuser: bool = False) -> Lawyer:
    firm, _ = LawFirm.objects.get_or_create(name="解析测试律所")
    return Lawyer.objects.create_user(
        username=username,
        password="p",
        is_admin=superuser,
        is_superuser=superuser,
        is_staff=superuser,
        law_firm=firm,
    )


def _client_for(user: Lawyer) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _make_task(owner: Lawyer | None, *, status: str = "completed", name: str = "起诉状.pdf") -> DocumentParsingTask:
    return DocumentParsingTask.objects.create(
        file_name=name,
        file_path=f"/tmp/{name}",
        file_size=1024,
        status=status,
        backend_used="paddle",
        text="解析出的全文内容",
        markdown="# 起诉状",
        metadata={"pages": 3},
        created_by=owner,
    )


@pytest.mark.django_db
class TestRecordsListOwnership:
    def test_normal_user_sees_own_and_legacy_only(self):
        owner = _make_user("owner1")
        other = _make_user("other1")
        own = _make_task(owner, name="我的解析.pdf")
        _make_task(other, name="别人的解析.pdf")
        legacy = _make_task(None, name="存量旧记录.pdf")  # created_by NULL 兼容口径

        resp = _client_for(owner).get("/api/v1/document-parsing/records")
        assert resp.status_code == 200
        data: dict[str, Any] = resp.json()
        names = [item["file_name"] for item in data["items"]]
        assert "我的解析.pdf" in names
        assert "存量旧记录.pdf" in names
        assert "别人的解析.pdf" not in names
        assert data["count"] == 2

    def test_admin_sees_all(self):
        owner = _make_user("owner2")
        admin = _make_user("admin2", superuser=True)
        _make_task(owner, name="普通用户的.pdf")
        _make_task(admin, name="管理员的.pdf")

        resp = _client_for(admin).get("/api/v1/document-parsing/records")
        assert resp.status_code == 200
        names = [i["file_name"] for i in resp.json()["items"]]
        assert set(names) == {"普通用户的.pdf", "管理员的.pdf"}

    def test_status_filter_and_pagination_fields(self):
        owner = _make_user("owner3")
        _make_task(owner, status="failed", name="失败任务.pdf")
        _make_task(owner, status="completed", name="成功任务.pdf")

        resp = _client_for(owner).get("/api/v1/document-parsing/records", {"status": "failed"})
        assert resp.status_code == 200
        data = resp.json()
        assert [i["file_name"] for i in data["items"]] == ["失败任务.pdf"]
        assert all(i["status"] == "failed" for i in data["items"])
        assert data["page"] == 1
        assert data["num_pages"] == 1


@pytest.mark.django_db
class TestRecordDetailOwnership:
    def test_owner_reads_full_detail(self):
        owner = _make_user("owner4")
        task = _make_task(owner, name="详情.pdf")

        resp = _client_for(owner).get(f"/api/v1/document-parsing/records/{task.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "解析出的全文内容"
        assert data["markdown"] == "# 起诉状"
        assert data["metadata"] == {"pages": 3}
        assert data["backend_used"] == "paddle"

    def test_foreign_record_404_for_normal_user(self):
        owner = _make_user("owner5")
        intruder = _make_user("intruder5")
        task = _make_task(owner, name="机密.pdf")

        resp = _client_for(intruder).get(f"/api/v1/document-parsing/records/{task.id}")
        assert resp.status_code == 404
        # 错误体不泄露记录内容（无 text/markdown 字段）
        body = resp.json()
        assert "解析出的全文内容" not in str(body)
        assert task.text  # 源数据仍在库中，仅被归属过滤拒绝

    def test_nonexistent_record_404(self):
        user = _make_user("owner6")
        resp = _client_for(user).get("/api/v1/document-parsing/records/99999999")
        assert resp.status_code == 404
        assert "99999999" in str(resp.json())  # 错误详情回显请求的记录 ID


@pytest.mark.django_db
class TestTaskStatusPolling:
    def test_completed_q_task_returns_success_payload(self):
        from django_q.models import Task

        owner = _make_user("owner7")
        # 本仓 django_q_task.id 为 varchar(32)（非 36 位 uuid 文本），取 32 字符串
        q_id = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
        q_task = Task.objects.create(
            id=q_id,
            name="parse",
            func="doc_parse_task",
            started=timezone.now() - timezone.timedelta(seconds=5),
            stopped=timezone.now(),
            success=True,
            result={"text": "队列结果"},
        )
        record = _make_task(owner, name="异步解析.pdf", status="processing")
        record.q_task_id = str(q_task.id)
        record.save(update_fields=["q_task_id"])

        resp = _client_for(owner).get(f"/api/v1/document-parsing/task/{record.id}")
        assert resp.status_code == 200
        data = resp.json()
        # 对外只回显记录 id 令牌，不暴露内部 Q id
        assert data["task_id"] == str(record.id)
        assert data["status"] == "success"
        assert data["result"] == {"text": "队列结果"}

    def test_unknown_token_404_for_normal_user(self):
        owner = _make_user("owner8")
        intruder = _make_user("intruder8")
        task = _make_task(owner, name="他人任务.pdf")

        # 令牌指向他人记录：归属过滤后按不存在处理，不泄露存在性
        resp = _client_for(intruder).get(f"/api/v1/document-parsing/task/{task.id}")
        assert resp.status_code == 404
        # 完全不存在的令牌同样 404
        resp_missing = _client_for(owner).get("/api/v1/document-parsing/task/42424242")
        assert resp_missing.status_code == 404
