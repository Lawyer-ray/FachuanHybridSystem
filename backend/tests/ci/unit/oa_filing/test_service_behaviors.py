"""oa_filing 行为测试（P2：以真实断言替换 import 冒烟）。

覆盖此前零覆盖的服务分支：
- _friendly_error_message：timeout/DNS/refused/未知异常 → 用户可读提示
- 会话属主隔离（安全审计 A-04 语义）：非属主读他人会话 = DoesNotExist、admin 豁免
- StampLookupService：空路径/.. 拒绝/绑定命中/未命中（此前整个服务零测试）
- import_session_service：get_credential 命中与缺失、会话 lawyer_id 过滤
- JTNAdapter 对五个 Protocol 的 runtime conformance
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.testing.factories import ContractFactory, LawyerFactory


def _make_credential(lawyer: Any, site_name: str = "金诚同达OA") -> Any:
    from apps.organization.models import AccountCredential

    return AccountCredential.objects.create(
        lawyer=lawyer, site_name=site_name, account="tester", password="secret"  # pragma: allowlist secret
    )


class TestFriendlyErrorMessage:
    def _f(self, message: str) -> str:
        from apps.oa_filing.services.script_executor_service import _friendly_error_message

        return _friendly_error_message(Exception(message))

    def test_timeout(self) -> None:
        assert "超时" in self._f("HTTPSConnectionPool: Read timed out")

    def test_dns_failure(self) -> None:
        assert "域名" in self._f("Failed to resolve 'oa.local': nodename nor servname provided")

    def test_connection_refused(self) -> None:
        assert "拒绝连接" in self._f("HTTPConnectionError: Connection refused")

    def test_unknown_passthrough(self) -> None:
        assert self._f("业务失败：字段缺失") == "业务失败：字段缺失"


@pytest.mark.django_db
class TestSessionOwnerIsolation:
    def _make_session(self, model: Any, **extra: Any) -> tuple[Any, Any]:
        owner = LawyerFactory()
        kwargs: dict[str, Any] = {"contract": ContractFactory(), "user": owner}
        if model.__name__ == "StampSession":
            kwargs.update(oa_case_number="OA-001", file_path="/tmp/x.pdf")
        kwargs.update(extra)
        return model.objects.create(**kwargs), owner

    def test_filing_session_owner_isolation(self) -> None:
        from django.core.exceptions import ObjectDoesNotExist

        from apps.oa_filing.models import FilingSession
        from apps.oa_filing.services.script_executor_service import ScriptExecutorService

        session, owner = self._make_session(FilingSession)
        other = LawyerFactory()
        svc = ScriptExecutorService()

        assert svc.get_session(session.id, owner).id == session.id
        with pytest.raises(ObjectDoesNotExist):
            svc.get_session(session.id, other)
        # admin 豁免可读他人会话
        admin = LawyerFactory(is_admin=True)
        assert svc.get_session(session.id, admin).id == session.id

    def test_stamp_session_owner_isolation(self) -> None:
        from django.core.exceptions import ObjectDoesNotExist

        from apps.oa_filing.models import StampSession
        from apps.oa_filing.services.script_executor_service import ScriptExecutorService

        session, owner = self._make_session(StampSession)
        other = LawyerFactory()
        svc = ScriptExecutorService()

        assert svc.get_stamp_session(session.id, owner).id == session.id
        with pytest.raises(ObjectDoesNotExist):
            svc.get_stamp_session(session.id, other)


@pytest.mark.django_db
class TestStampLookupService:
    def _svc(self) -> Any:
        from apps.oa_filing.services.stamp_lookup_service import StampLookupService

        return StampLookupService()

    def test_empty_path_rejected(self) -> None:
        from apps.oa_filing.services.stamp_lookup_service import StampLookupError

        with pytest.raises(StampLookupError, match="为空"):
            self._svc().lookup_by_file_path("   ")

    def test_dotdot_rejected(self) -> None:
        from apps.oa_filing.services.stamp_lookup_service import StampLookupError

        with pytest.raises(StampLookupError, match=r"\.\."):
            self._svc().lookup_by_file_path("/data/contracts/../etc/passwd")

    def test_contract_binding_hit(self, tmp_path: Any) -> None:
        from apps.contracts.models import ContractFolderBinding
        from apps.oa_filing.services.stamp_lookup_service import StampLookupService

        contract = ContractFactory(law_firm_oa_case_number="OA-STAMP-1")
        ContractFolderBinding.objects.create(contract=contract, folder_path=str(tmp_path))
        target = tmp_path / "盖章文件.pdf"
        target.write_bytes(b"%PDF-0")

        result = StampLookupService.lookup_by_file_path(str(target))
        assert result.contract_id == contract.id
        assert result.oa_case_number == "OA-STAMP-1"
        assert result.file_path == str(target)

    def test_no_binding_raises(self, tmp_path: Any) -> None:
        from apps.oa_filing.services.stamp_lookup_service import StampLookupError, StampLookupService

        target = tmp_path / "孤儿文件.pdf"
        target.write_bytes(b"%PDF-0")
        with pytest.raises(StampLookupError, match="无法根据文件路径"):
            StampLookupService.lookup_by_file_path(str(target))

    def test_escape_out_of_binding_dir_rejected(self, tmp_path: Any) -> None:
        """绑定目录外的同名路径不得命中（安全审计 B-18）。"""
        from apps.contracts.models import ContractFolderBinding
        from apps.oa_filing.services.stamp_lookup_service import StampLookupError, StampLookupService

        bound = tmp_path / "bound"
        bound.mkdir()
        contract = ContractFactory(law_firm_oa_case_number="OA-STAMP-2")
        ContractFolderBinding.objects.create(contract=contract, folder_path=str(bound))
        # 真实存在于绑定目录外、但目录名拼进 parents 前缀的文件（符号链接越界场景的直译）
        outside = tmp_path / "bound-escape" / "文件.pdf"
        outside.parent.mkdir()
        outside.write_bytes(b"%PDF-0")
        with pytest.raises(StampLookupError):
            StampLookupService.lookup_by_file_path(str(outside))


@pytest.mark.django_db
class TestImportSessionService:
    def test_get_credential_found_and_missing(self) -> None:
        from apps.oa_filing.services.import_session_service import get_credential

        lawyer = LawyerFactory()
        assert get_credential(lawyer.id, "金诚同达OA") is None
        cred = _make_credential(lawyer)
        found = get_credential(lawyer.id, "金诚同达OA")
        assert found is not None and found.id == cred.id

    def test_case_session_lawyer_scoping(self) -> None:
        from apps.oa_filing.models import CaseImportSession
        from apps.oa_filing.services.import_session_service import get_case_session_or_none

        owner = LawyerFactory()
        session = CaseImportSession.objects.create(lawyer=owner, credential=None, uploaded_filename="a.xlsx")
        other = LawyerFactory()

        assert get_case_session_or_none(session.id, lawyer_id=owner.id) is not None
        assert get_case_session_or_none(session.id, lawyer_id=other.id) is None
        # 不带 lawyer_id 的内部调用仍可读
        assert get_case_session_or_none(session.id) is not None


class TestJtnAdapterProtocolConformance:
    def test_satisfies_all_protocols(self) -> None:
        from apps.oa_filing.services.base_firm_adapter import (
            ArchiveAdapter,
            CaseImportAdapter,
            ClientImportAdapter,
            ConflictCheckAdapter,
            FilingAdapter,
            StampAdapter,
        )
        from apps.oa_filing.services.oa_firm_registry import create_adapter

        adapter = create_adapter("金诚同达OA", account="tester", password="secret")  # pragma: allowlist secret
        for protocol in (
            FilingAdapter,
            StampAdapter,
            ArchiveAdapter,
            ConflictCheckAdapter,
            CaseImportAdapter,
            ClientImportAdapter,
        ):
            assert isinstance(adapter, protocol), f"JTNAdapter 未实现 {protocol.__name__}"
