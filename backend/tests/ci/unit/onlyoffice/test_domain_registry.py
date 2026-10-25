"""OnlyOffice 业务域注册表测试。

**为什么要这层**：`EditorSession.task_type` 早就预留了「其它业务域」，但实现里
三处写死 `"contract_review"`（保存回写、取文件代理、内容版本）。起诉状 /
答辩状 / 和解协议同属「AI 出建议 + 律师逐条决策」，复用复审台时不必去改
三个分散的位置、也不重复写权限口径。

重点：
- 内置 contract_review 域可解析下载路径；
- 未知路径不被任何域认领（代理不放行）；
- 权限口径统一：属主或超管，其余一律拒绝；
- 新业务域只需注册，不改调用点。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from apps.onlyoffice.services.domain_registry import (
    OODomain,
    all_domains,
    domain_for_path,
    get_domain,
    is_owner_or_admin,
    register_domain,
)


class TestBuiltinDomain:
    def test_contract_review_registered(self) -> None:
        d = get_domain("contract_review")
        assert d is not None
        assert d.key == "contract_review"

    def test_parses_download_paths(self) -> None:
        tid = uuid4()
        for which in ("download", "download-original"):
            hit = domain_for_path(f"/api/v1/contract-review/{tid}/{which}")
            assert hit is not None
            domain, parsed_id, parsed_which = hit
            assert domain.key == "contract_review"
            assert parsed_id == tid
            assert parsed_which == which

    def test_rejects_unrelated_paths(self) -> None:
        assert domain_for_path("/api/v1/inbox/messages/1/attachments/0/download") is None
        assert domain_for_path("/api/v1/contract-review/not-a-uuid/download") is None
        assert domain_for_path("") is None


class TestPermissionPolicy:
    class _User:
        def __init__(self, pk: int, superuser: bool = False) -> None:
            self.pk = pk
            self.is_superuser = superuser

    def test_owner_allowed(self) -> None:
        assert is_owner_or_admin(self._User(7), 7) is True

    def test_superuser_allowed(self) -> None:
        assert is_owner_or_admin(self._User(1, superuser=True), 999) is True

    def test_other_user_denied(self) -> None:
        assert is_owner_or_admin(self._User(8), 7) is False

    def test_anonymous_denied(self) -> None:
        assert is_owner_or_admin(None, 7) is False

    def test_missing_owner_denied(self) -> None:
        assert is_owner_or_admin(self._User(7), None) is False


class TestExtensibility:
    """新业务域（如起诉状）只注册，不改 file_proxy / callback_service。"""

    def test_register_new_domain(self) -> None:
        tid = uuid4()

        def _noop(*a: Any, **k: Any) -> Any:
            return None

        register_domain(
            OODomain(
                key="litigation_doc",
                path_pattern=r"^/api/v1/litigation/docs/([0-9a-f-]{36})/(download-original|download)(?:\?|$)",
                get_owner_id=lambda t: getattr(t, "user_id", None),
                resolve_file=_noop,
                adopt_edited=_noop,
            )
        )
        hit = domain_for_path(f"/api/v1/litigation/docs/{tid}/download")
        assert hit is not None
        assert hit[0].key == "litigation_doc"
        assert hit[1] == tid

        # 收尾：不留状态给别的测试
        from apps.onlyoffice.services import domain_registry as reg

        reg._registry.pop("litigation_doc", None)

    def test_all_domains_includes_builtin(self) -> None:
        keys = [d.key for d in all_domains()]
        assert "contract_review" in keys
