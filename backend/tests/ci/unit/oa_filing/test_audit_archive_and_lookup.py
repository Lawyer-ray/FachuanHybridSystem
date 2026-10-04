"""oa_filing 安全审计测试：归档 file_paths 全量校验 + lookup 端点越权。

- execute_archive：file_paths 中每个路径都必须通过 lookup（.. 拒绝/绑定目录收敛）
  与合同归属校验——修复「只校 file_paths[0]、其余路径被上传到外部 OA」的外带
- /oa-stamp/lookup、/oa-archive/lookup：无权与未命中返回同款 404，防探测
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.testing.factories import ContractFactory, LawyerFactory


def _make_credential(lawyer: Any, site_name: str = "金诚同达OA") -> Any:
    from apps.organization.models import AccountCredential

    return AccountCredential.objects.create(
        lawyer=lawyer,
        site_name=site_name,
        account="tester",
        password="secret",  # pragma: allowlist secret
    )


def _bind_contract_folder(contract: Any, folder: Any) -> None:
    from apps.contracts.models import ContractFolderBinding

    ContractFolderBinding.objects.create(contract=contract, folder_path=str(folder))


@pytest.mark.django_db
class TestExecuteArchiveValidatesAllPaths:
    def _setup(self, tmp_path: Any):
        owner = LawyerFactory()
        _make_credential(owner)
        contract = ContractFactory(law_firm_oa_case_number="OA-ARCH-1")
        folder = tmp_path / "archive"
        folder.mkdir()
        _bind_contract_folder(contract, folder)
        good = folder / "卷宗.pdf"
        good.write_bytes(b"%PDF-0")
        return owner, contract, folder, good

    def test_second_path_outside_binding_rejected(self, tmp_path: Any) -> None:
        """第二个路径不在任何绑定目录内 → 整个请求被拒（修复前会原样入 session 外带）。"""
        from apps.oa_filing.services.script_executor_service import ScriptExecutorService
        from apps.oa_filing.services.stamp_lookup_service import StampLookupError

        owner, contract, folder, good = self._setup(tmp_path)
        outside = tmp_path / "outside"
        outside.mkdir()
        evil = outside / "敏感文件.pdf"
        evil.write_bytes(b"%PDF-evil")

        with pytest.raises(StampLookupError):
            ScriptExecutorService().execute_archive([str(good), str(evil)], owner)

        from apps.oa_filing.models import ArchiveSession

        assert not ArchiveSession.objects.filter(contract=contract).exists()

    def test_second_path_dotdot_rejected(self, tmp_path: Any) -> None:
        """第二个路径含 .. → 整个请求被拒。"""
        from apps.oa_filing.services.script_executor_service import ScriptExecutorService
        from apps.oa_filing.services.stamp_lookup_service import StampLookupError

        owner, contract, folder, good = self._setup(tmp_path)
        evil = str(folder / ".." / "escape.pdf")

        with pytest.raises(StampLookupError):
            ScriptExecutorService().execute_archive([str(good), evil], owner)

    def test_paths_of_different_contracts_rejected(self, tmp_path: Any) -> None:
        """两个路径分属不同合同 → 拒绝（session 单合同语义）。"""
        from apps.oa_filing.services.exceptions import ScriptExecutionError
        from apps.oa_filing.services.script_executor_service import ScriptExecutorService

        owner, contract, folder, good = self._setup(tmp_path)
        other_contract = ContractFactory(law_firm_oa_case_number="OA-ARCH-2")
        other_folder = tmp_path / "other"
        other_folder.mkdir()
        _bind_contract_folder(other_contract, other_folder)
        other_file = other_folder / "他合同文件.pdf"
        other_file.write_bytes(b"%PDF-1")

        with pytest.raises(ScriptExecutionError, match="不同合同"):
            ScriptExecutorService().execute_archive([str(good), str(other_file)], owner)

    def test_all_paths_contract_access_enforced(self, tmp_path: Any) -> None:
        """即使第一个路径合法，用户对合同无权（他人指派）仍被拒。"""
        from apps.contracts.models import ContractAssignment
        from apps.core.exceptions import PermissionDenied
        from apps.oa_filing.services.script_executor_service import ScriptExecutorService

        owner, contract, folder, good = self._setup(tmp_path)
        intruder = LawyerFactory()
        _make_credential(intruder)
        other_lawyer = LawyerFactory()
        ContractAssignment.objects.create(contract=contract, lawyer=other_lawyer)

        with pytest.raises(PermissionDenied):
            ScriptExecutorService().execute_archive([str(good)], intruder)


@pytest.mark.django_db
class TestLookupEndpointsAccess:
    def _binding_file(self, tmp_path: Any):
        contract = ContractFactory(law_firm_oa_case_number="OA-LOOKUP-1")
        folder = tmp_path / "lookup"
        folder.mkdir()
        _bind_contract_folder(contract, folder)
        target = folder / "材料.pdf"
        target.write_bytes(b"%PDF-0")
        return contract, target

    def _login(self, username: str):
        from django.test import Client

        from apps.organization.models import Lawyer

        user = Lawyer.objects.create_user(username=username, password="pass12345")
        client = Client()
        client.force_login(user)
        return client, user

    def test_stamp_lookup_no_access_same_as_miss(self, tmp_path: Any) -> None:
        """无权用户 lookup 得到与未命中一致的 404，不泄露合同存在性。"""
        contract, target = self._binding_file(tmp_path)
        client, _ = self._login("lookup_intruder")

        miss = client.post(
            "/api/v1/oa-stamp/lookup",
            data=json.dumps({"file_path": str(tmp_path / "不存在.pdf")}),
            content_type="application/json",
        )
        denied = client.post(
            "/api/v1/oa-stamp/lookup",
            data=json.dumps({"file_path": str(target)}),
            content_type="application/json",
        )

        assert miss.status_code == 404
        assert denied.status_code == 404
        # 响应体一致（envelope 含每次请求唯一的 request_id/trace_id，剔除后比较）
        miss_body = {k: v for k, v in miss.json().items() if k not in ("request_id", "trace_id")}
        denied_body = {k: v for k, v in denied.json().items() if k not in ("request_id", "trace_id")}
        assert miss_body == denied_body

    def test_stamp_lookup_authorized_returns_contract(self, tmp_path: Any) -> None:
        """对合同有权的用户（如 admin 看无指派合同）lookup 正常返回。"""
        contract, target = self._binding_file(tmp_path)
        client, admin = self._login("lookup_admin")
        from apps.organization.models import LawFirm

        admin.is_admin = True
        admin.law_firm = LawFirm.objects.create(name="lookup所")
        admin.save()

        resp = client.post(
            "/api/v1/oa-stamp/lookup",
            data=json.dumps({"file_path": str(target)}),
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["contract_id"] == contract.id
        assert data["oa_case_number"] == "OA-LOOKUP-1"

    def test_archive_lookup_no_access_same_as_miss(self, tmp_path: Any) -> None:
        contract, target = self._binding_file(tmp_path)
        client, _ = self._login("arch_lookup_intruder")

        miss = client.post(
            "/api/v1/oa-archive/lookup",
            data=json.dumps({"file_paths": [str(tmp_path / "不存在.pdf")]}),
            content_type="application/json",
        )
        denied = client.post(
            "/api/v1/oa-archive/lookup",
            data=json.dumps({"file_paths": [str(target)]}),
            content_type="application/json",
        )

        assert miss.status_code == 404
        assert denied.status_code == 404
        miss_body = {k: v for k, v in miss.json().items() if k not in ("request_id", "trace_id")}
        denied_body = {k: v for k, v in denied.json().items() if k not in ("request_id", "trace_id")}
        assert miss_body == denied_body
