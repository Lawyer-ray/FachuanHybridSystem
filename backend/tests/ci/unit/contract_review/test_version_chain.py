"""文档版本链测试。

**为什么不再靠文件名**：`[修订版]V1_日期` 这种约定改个名就断链，排序也只对
同一天有效。版本链把它变成真实关系：节点 + parent + 单调序号。

重点：
- 链头是客户来稿，AI 产物接在它后面；
- 编辑器保存再接一个节点（律师编辑版）；
- 重跑流水线不重复建链头；
- 序号在任务内唯一且单调（跨任务互不干扰）。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.contract_review.models.document_version import DocumentVersion, VersionKind
from apps.contract_review.models.review_task import ReviewTask
from apps.contract_review.services.review.version_chain import ensure_original_version, list_versions, record_version

pytestmark = pytest.mark.django_db


@pytest.fixture
def task() -> ReviewTask:
    from apps.testing.factories import LawyerFactory

    return ReviewTask.objects.create(user=LawyerFactory(username="ver_owner"), original_file="contract_review/uploads/src.docx")


@pytest.fixture
def api_client(task: ReviewTask) -> Any:
    """带 JWT 的客户端，绑定到 task 的属主（否则版本链接口一律 403）。"""
    from django.test import Client
    from ninja_jwt.tokens import RefreshToken

    c = Client()
    c.defaults["HTTP_AUTHORIZATION"] = f"Bearer {RefreshToken.for_user(task.user).access_token}"
    return c


class TestVersionChain:
    def test_original_is_chain_head(self, task: ReviewTask) -> None:
        head = ensure_original_version(task_id=task.id, file_path="uploads/src.docx", file_name="客户来稿.docx")
        assert head is not None
        assert head.kind == VersionKind.ORIGINAL
        assert head.version_no == 1
        assert head.parent_id is None, "链头没有父节点"

    def test_ensure_original_is_idempotent(self, task: ReviewTask) -> None:
        """重跑流水线不能重复建链头，否则链上出现两个「客户来稿」。"""
        a = ensure_original_version(task_id=task.id, file_path="uploads/src.docx")
        b = ensure_original_version(task_id=task.id, file_path="uploads/src.docx")
        assert a is not None and b is not None
        assert a.id == b.id
        assert DocumentVersion.objects.filter(task=task, kind=VersionKind.ORIGINAL).count() == 1

    def test_ai_version_follows_original(self, task: ReviewTask) -> None:
        ensure_original_version(task_id=task.id, file_path="uploads/src.docx")
        ai = record_version(
            task_id=task.id,
            kind=VersionKind.AI,
            file_path="outputs/AI.docx",
            file_name="合同[修订版]V1_20261025.docx",
            author="法穿SI",
        )
        assert ai.version_no == 2
        assert ai.parent is not None, "AI 版必须指向它改自的那一版（客户来稿）"
        assert ai.parent.kind == VersionKind.ORIGINAL

    def test_lawyer_save_appends_and_points_to_latest(self, task: ReviewTask) -> None:
        ensure_original_version(task_id=task.id, file_path="uploads/src.docx")
        ai = record_version(task_id=task.id, kind=VersionKind.AI, file_path="outputs/AI.docx")
        saved = record_version(
            task_id=task.id,
            kind=VersionKind.LAWYER,
            file_path="outputs/AI-律编v1.docx",
            author="张律师",
            note="编辑器保存 v1",
        )
        assert saved.version_no == 3
        assert saved.parent_id == ai.id, "保存版接在当前最新版之后"

    def test_versions_are_ordered_and_unique(self, task: ReviewTask) -> None:
        ensure_original_version(task_id=task.id, file_path="u.docx")
        for i in range(3):
            record_version(task_id=task.id, kind=VersionKind.LAWYER, file_path=f"o{i}.docx")
        rows = list_versions(task.id)
        assert [r["version_no"] for r in rows] == [1, 2, 3, 4]
        assert len({r["version_no"] for r in rows}) == 4

    def test_chains_are_per_task(self, task: ReviewTask, db: Any) -> None:
        """两个任务各自从 V1 开始，序号互不影响。"""
        from apps.testing.factories import LawyerFactory

        other = ReviewTask.objects.create(
            user=LawyerFactory(username="ver_other_task"), original_file="contract_review/uploads/b.docx"
        )
        ensure_original_version(task_id=task.id, file_path="a.docx")
        record_version(task_id=task.id, kind=VersionKind.AI, file_path="a1.docx")
        ensure_original_version(task_id=other.id, file_path="b.docx")

        assert list_versions(task.id)[0]["version_no"] == 1
        assert len(list_versions(other.id)) == 1
        assert list_versions(other.id)[0]["version_no"] == 1

    def test_kind_labels_are_human_readable(self, task: ReviewTask) -> None:
        """前端版本链面板直接展示 kind_label，不能是英文枚举。"""
        ensure_original_version(task_id=task.id, file_path="u.docx")
        record_version(task_id=task.id, kind=VersionKind.AI, file_path="a.docx")
        labels = [r["kind_label"] for r in list_versions(task.id)]
        assert labels == ["客户来稿", "AI 修订版"]


class TestVersionEndpoint:
    def test_returns_chain(self, task: ReviewTask, api_client: Any) -> None:
        ensure_original_version(task_id=task.id, file_path="u.docx")
        record_version(task_id=task.id, kind=VersionKind.AI, file_path="a.docx")

        r = api_client.get(f"/api/v1/contract-review/{task.id}/versions")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        assert body["items"][0]["kind"] == "original"
        assert body["items"][1]["kind"] == "ai"

    def test_missing_task_is_404(self, api_client: Any) -> None:
        import uuid

        r = api_client.get(f"/api/v1/contract-review/{uuid.uuid4()}/versions")
        assert r.status_code == 404

    def test_other_user_forbidden(self, task: ReviewTask) -> None:
        from django.test import Client
        from ninja_jwt.tokens import RefreshToken

        from apps.testing.factories import LawyerFactory

        ensure_original_version(task_id=task.id, file_path="u.docx")
        other = LawyerFactory(username="ver_other")
        c = Client()
        c.defaults["HTTP_AUTHORIZATION"] = f"Bearer {RefreshToken.for_user(other).access_token}"
        r = c.get(f"/api/v1/contract-review/{task.id}/versions")
        assert r.status_code == 403
