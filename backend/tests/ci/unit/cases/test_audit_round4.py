"""第四轮审查修复回归测试（cases 域）。

覆盖：
- PUT/DELETE 端点补传 org_access/perm_open_access（丢权限上下文修复）
- 列表 status/case_type 过滤改用 Case 自身字段（无合同案件不再被丢）
- 邮件附件导入：附件上传失败不标记 source_subfolder（重跑可补）
- REST 建案 is_filed=True 自动补生成建档编号（失败不阻断建案）
- CaseUpdate.status 枚举校验（非法值 422）
- folder_scan 任务提交失败时 session 置 FAILED（不再卡 PENDING）
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.models import Case, CaseFolderScanSession, CaseFolderScanStatus, CaseLog
from apps.cases.services.case.case_command_service import CaseCommandService
from apps.cases.services.case.case_search_service import CaseSearchService
from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
from apps.cases.services.material.folder_scan_service import CaseFolderScanService
from apps.core.models.enums import CaseStatus, SimpleCaseType
from apps.testing.factories import CaseFactory, CaseLogFactory, LawyerFactory

# ── Item 1: PUT/DELETE 端点透传访问上下文 ────────────────────────────────────────


class TestCaseApiForwardsAccessContext:
    """API 层不再丢 org_access/perm_open_access（与 GET 口径对齐）。"""

    @pytest.mark.asyncio
    async def test_update_case_endpoint_forwards_context(self):
        from apps.cases.api import case_api
        from apps.cases.schemas import CaseUpdate

        user = MagicMock(name="lawyer")
        org_access = {"extra_cases": {42}}
        request = SimpleNamespace(user=user, org_access=org_access, perm_open_access=False)
        payload = CaseUpdate(name="新名字")

        mock_service = MagicMock()
        with (
            patch.object(case_api, "_get_case_mutation_facade", return_value=mock_service),
            patch.object(case_api, "_serialize_case", return_value={"id": 42}),
        ):
            await case_api.update_case(request, 42, payload)

        mock_service.update_case.assert_called_once_with(
            42, {"name": "新名字"}, user=user, org_access=org_access, perm_open_access=False
        )

    @pytest.mark.asyncio
    async def test_delete_case_endpoint_forwards_context(self):
        from apps.cases.api import case_api

        user = MagicMock(name="lawyer")
        org_access = {"extra_cases": {42}}
        request = SimpleNamespace(user=user, org_access=org_access, perm_open_access=False)

        mock_service = MagicMock()
        with patch.object(case_api, "_get_case_mutation_facade", return_value=mock_service):
            result = await case_api.delete_case(request, 42)

        assert result == {"success": True}
        mock_service.delete_case.assert_called_once_with(42, user=user, org_access=org_access, perm_open_access=False)


@pytest.mark.django_db
class TestUpdateCaseWithOrgAccess:
    def test_authorized_by_org_access_can_update(self):
        """授权用户（org_access 含该案）update 成功——修复前 API 只传 user 会 403。"""
        lawyer = LawyerFactory()
        case = CaseFactory()
        service = CaseCommandService()

        updated = service.update_case(
            case.id,
            {"name": "改名后的案件"},
            user=lawyer,
            org_access={"extra_cases": {case.id}},
            perm_open_access=False,
        )

        assert updated.name == "改名后的案件"
        case.refresh_from_db()
        assert case.name == "改名后的案件"

    def test_unauthorized_user_rejected(self):
        """无 org_access 且无指派的普通用户 update 被拒（403 语义）。"""
        from apps.core.exceptions import ForbiddenError

        lawyer = LawyerFactory()
        case = CaseFactory()
        service = CaseCommandService()

        with pytest.raises(ForbiddenError):
            service.update_case(case.id, {"name": "x"}, user=lawyer, org_access=None, perm_open_access=False)


# ── Item 2: 列表过滤用 Case 自身字段 ───────────────────────────────────────────


@pytest.mark.django_db
class TestListCasesFiltersOnCaseFields:
    def test_status_filter_keeps_contractless_cases(self):
        """无合同关联的案件按 Case.status 过滤时不再被丢。"""
        # CaseFactory 不支持 contract=None（会自动补合同），这里直接建模型行
        with_contract = CaseFactory(status=CaseStatus.ACTIVE)
        active_no_contract = Case.objects.create(name="无合同在办", status=CaseStatus.ACTIVE, contract=None)
        Case.objects.create(name="无合同结案", status=CaseStatus.CLOSED, contract=None)

        service = CaseSearchService()
        ids = {c.id for c in service.list_cases(status=CaseStatus.ACTIVE, perm_open_access=True)}

        assert active_no_contract.id in ids
        assert with_contract.id in ids
        assert Case.objects.get(name="无合同结案").id not in ids

    def test_case_type_filter_uses_case_field(self):
        """case_type 过滤打在 Case.case_type（而非 contract__case_type）。"""
        criminal = Case.objects.create(
            name="无合同刑事", status=CaseStatus.ACTIVE, contract=None, case_type=SimpleCaseType.CRIMINAL
        )
        Case.objects.create(name="无合同民事", status=CaseStatus.ACTIVE, contract=None, case_type=SimpleCaseType.CIVIL)

        service = CaseSearchService()
        got = list(service.list_cases(case_type=SimpleCaseType.CRIMINAL, perm_open_access=True))

        assert {c.id for c in got} == {criminal.id}
        assert all(c.case_type == SimpleCaseType.CRIMINAL for c in got)


# ── Item 4: 附件导入失败不标记已导入 ───────────────────────────────────────────


@pytest.mark.django_db
class TestEmailImportAttachmentFailure:
    def test_failed_upload_not_marked_imported(self, tmp_path: Path):
        """附件上传失败时 source_subfolder 不落库，重跑可补传。"""
        case = CaseFactory()
        (tmp_path / "emails").mkdir()
        sub = tmp_path / "2024-03-20-原告回复"
        sub.mkdir()
        (sub / "a.pdf").write_bytes(b"a")

        svc = EmailFolderScanService()
        mutation = MagicMock()
        mutation.create_log.return_value = CaseLogFactory(case=case)

        with (
            patch.object(svc, "_get_bound_case_root", return_value=(tmp_path, None)),
            patch.object(svc, "_collect_subdirs", return_value=[(sub, [sub / "a.pdf"])]),
            patch.object(svc, "_mutation_service", mutation),
            patch.object(svc, "_upload_file_as_attachment", return_value=None),
        ):
            result = svc.import_email_folder(case_id=case.id, subfolder="emails")

        assert len(result["logs"]) == 1
        failed_log = result["logs"][0]
        failed_log.refresh_from_db()
        assert failed_log.source_subfolder == ""

    def test_successful_upload_marks_imported(self, tmp_path: Path):
        """附件全部上传成功时才标记 source_subfolder。"""
        case = CaseFactory()
        (tmp_path / "emails").mkdir()
        sub = tmp_path / "2024-03-21-被告答辩"
        sub.mkdir()
        (sub / "b.pdf").write_bytes(b"b")

        svc = EmailFolderScanService()
        mutation = MagicMock()
        mutation.create_log.return_value = CaseLogFactory(case=case)
        attachment = MagicMock()

        with (
            patch.object(svc, "_get_bound_case_root", return_value=(tmp_path, None)),
            patch.object(svc, "_collect_subdirs", return_value=[(sub, [sub / "b.pdf"])]),
            patch.object(svc, "_mutation_service", mutation),
            patch.object(svc, "_upload_file_as_attachment", return_value=attachment),
        ):
            svc.import_email_folder(case_id=case.id, subfolder="emails")

        created = mutation.create_log.return_value
        created.refresh_from_db()
        assert created.source_subfolder == "emails/2024-03-21-被告答辩"


# ── Item 5: 建案时补生成建档编号 ───────────────────────────────────────────────


@pytest.mark.django_db
class TestCreateCaseFilingNumber:
    def test_is_filed_generates_filing_number(self):
        lawyer = LawyerFactory()
        case = CaseCommandService().create_case(
            {
                "name": "建档案件",
                "case_type": SimpleCaseType.CIVIL,
                "status": CaseStatus.ACTIVE,
                "is_filed": True,
            },
            user=lawyer,
            perm_open_access=True,
        )
        assert case.filing_number
        assert case.filing_number.startswith(f"{case.start_date.year}_民事_AJ_")
        case.refresh_from_db()
        assert case.filing_number

    def test_not_filed_skips_filing_number(self):
        case = CaseCommandService().create_case(
            {"name": "未建档案件", "case_type": SimpleCaseType.CIVIL, "status": CaseStatus.ACTIVE},
            user=LawyerFactory(),
            perm_open_access=True,
        )
        assert not case.filing_number

    def test_generation_failure_does_not_abort_create(self):
        """编号生成失败只记日志，案件仍创建、编号留空。"""
        from apps.cases.services.number import CaseFilingNumberService

        with patch.object(
            CaseFilingNumberService, "generate_case_filing_number_internal", side_effect=RuntimeError("boom")
        ):
            case = CaseCommandService().create_case(
                {
                    "name": "自愈案件",
                    "case_type": SimpleCaseType.CIVIL,
                    "status": CaseStatus.ACTIVE,
                    "is_filed": True,
                },
                user=LawyerFactory(),
                perm_open_access=True,
            )

        assert Case.objects.filter(pk=case.pk).exists()
        case.refresh_from_db()
        assert not case.filing_number


# ── Item 6: CaseUpdate.status 枚举校验 ─────────────────────────────────────────


class TestCaseUpdateStatusValidation:
    def test_valid_status_accepted(self):
        from apps.cases.schemas import CaseUpdate

        assert CaseUpdate(status="active").status == "active"
        assert CaseUpdate(status="closed").status == "closed"

    def test_invalid_status_rejected(self):
        from pydantic import ValidationError

        from apps.cases.schemas import CaseUpdate

        with pytest.raises(ValidationError):
            CaseUpdate(status="bogus")

    def test_none_status_still_allowed(self):
        from apps.cases.schemas import CaseUpdate

        assert CaseUpdate().status is None


# ── Item 7: folder_scan 提交失败置 FAILED ─────────────────────────────────────


@pytest.mark.django_db
class TestFolderScanSubmitFailure:
    def test_submit_failure_marks_session_failed(self):
        case = CaseFactory()
        binding = MagicMock()
        binding.resolved_folder_path = "/tmp/nonexistent"

        svc = CaseFolderScanService()
        with (
            patch("apps.cases.services.material.folder_scan_service._ensure_case_exists"),
            patch("apps.cases.services.material.folder_scan_service._get_accessible_binding", return_value=binding),
            patch.object(svc, "_make_provider_for_binding", return_value=None),
            patch.object(svc, "_resolve_scan_scope", return_value={"scan_subfolder": "", "scan_folder": "/tmp"}),
            patch(
                "apps.cases.services.material.folder_scan_service.build_task_submission_service",
                side_effect=RuntimeError("qcluster down"),
            ),
        ):
            session = svc.start_scan(case_id=case.id, started_by=None)

        session.refresh_from_db()
        assert session.status == CaseFolderScanStatus.FAILED
        assert "任务提交失败" in session.error_message
