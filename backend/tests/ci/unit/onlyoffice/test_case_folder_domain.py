"""case_folder 业务域：让 OnlyOffice 能直接预览/编辑案件绑定文件夹里的文件。

**为什么需要**：诉讼详情页的文件主体在案件绑定目录（起诉状、证据、判决书），
合同常常没绑文件夹。只注册 contract_folder 时，案件文件夹里的 docx 点开仍是
「window.open 下载」老逻辑。注册进代理白名单后，DS 能拉案件文件，律师在
详情页右栏直接看、就地改，保存回写原地覆写——与合同文件夹完全同构
（共用 `_bound_folder_domain` 工厂）。

重点：
- 路径能解析出 case_id + subpath，且不与 contract_folder / contract_review 抢路径；
- 取文件走 CaseFolderBrowseService 的 ACL（代理不能比 REST 宽松）；
- 保存回写覆写原文件，subpath 双层编码要解开。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apps.onlyoffice.services.domain_registry import domain_for_path, get_domain


class TestCaseFolderPath:
    def test_registered(self) -> None:
        assert get_domain("case_folder") is not None

    def test_parses_case_and_subpath(self) -> None:
        hit = domain_for_path("/api/v1/cases/399/folder-file?subpath=2-%E8%AF%89%E7%8A%B6/a.docx")
        assert hit is not None
        domain, case_id, subpath = hit
        assert domain.key == "case_folder"
        assert case_id == 399
        # Django 解析 query 时已解码一次，这里拿到的是解码后的原文
        assert subpath == "2-%E8%AF%89%E7%8A%B6/a.docx"

    def test_subpath_with_extra_query_params(self) -> None:
        """下载票据会追加 &ticket=…，subpath 之后还有参数也必须能解析。"""
        hit = domain_for_path("/api/v1/cases/7/folder-file?subpath=x.docx&ticket=abc123")
        assert hit is not None
        assert hit[1] == 7
        assert hit[2] == "x.docx"

    def test_does_not_swallow_contract_folder_paths(self) -> None:
        """两个文件夹域的正则不能互相抢：合同路径必须仍归 contract_folder。"""
        hit = domain_for_path("/api/v1/contracts/318/folder-file?subpath=a.docx")
        assert hit is not None
        assert hit[0].key == "contract_folder"

    def test_does_not_swallow_contract_review_paths(self) -> None:
        hit = domain_for_path("/api/v1/contract-review/6f1e0000-0000-0000-0000-000000000000/download")
        assert hit is not None
        assert hit[0].key == "contract_review"


class TestCaseFolderFileResolution:
    """取文件必须沿用原端点 ACL（CaseAccessPolicy 在 service 内），代理不能放宽权限。"""

    @pytest.mark.django_db
    def test_unauthorized_user_gets_none(self, monkeypatch: Any) -> None:
        """ACL 拒绝时返回 None（对 DS 表现为 404，不是 500 无限重试）。"""
        domain = get_domain("case_folder")
        assert domain is not None and domain.resolve_for_proxy is not None

        def boom(_self: Any, **_kw: Any) -> Any:
            raise PermissionError("无权访问该案件")

        from apps.cases.services.material import case_folder_browse_service as mod

        monkeypatch.setattr(mod.CaseFolderBrowseService, "resolve_file", boom, raising=False)

        assert domain.resolve_for_proxy(object(), 399, "a.docx") is None

    @pytest.mark.django_db
    def test_returns_path_when_allowed(self, monkeypatch: Any, tmp_path: Path) -> None:
        domain = get_domain("case_folder")
        assert domain is not None and domain.resolve_for_proxy is not None

        f = tmp_path / "起诉状.docx"
        f.write_bytes(b"PK\x03\x04")

        from apps.cases.services.material import case_folder_browse_service as mod

        monkeypatch.setattr(mod.CaseFolderBrowseService, "resolve_file", lambda _self, **_kw: f, raising=False)
        assert domain.resolve_for_proxy(object(), 399, "a.docx") == f


class TestCaseFolderSaveWriteback:
    """「原地改、原地存」：回写必须真的覆写案件文件夹里的那一份。"""

    @pytest.mark.django_db
    def test_adopt_edited_writes_back_to_source_file(self, monkeypatch: Any) -> None:
        """从 session.source_path 反解 case + subpath，覆写那一份。"""
        domain = get_domain("case_folder")
        assert domain is not None

        called: dict[str, Any] = {}

        def fake_save(_self: Any, **kw: Any) -> dict[str, Any]:
            called.update(kw)
            return {"subpath": kw["subpath"], "name": "a.docx", "size": len(kw["data"])}

        from apps.cases.services.material import case_folder_browse_service as mod

        monkeypatch.setattr(mod.CaseFolderBrowseService, "save_file_content", fake_save, raising=False)

        class _S:
            task_type = "case_folder"
            # 真实会话里 source_path 就是当初打开的站内路径（subpath 已 urlencode）
            source_path = "/api/v1/cases/399/folder-file?subpath=2-%E8%AF%89%E7%8A%B6/a.docx"
            user = None

        domain.adopt_edited(_S(), b"newbytes", 1)

        assert called["owner_id"] == 399
        # 双层编码要解开，否则写到一个名字带 % 的错位置
        assert called["subpath"] == "2-诉状/a.docx"
        assert called["data"] == b"newbytes"
        # 回写不校验 mtime：这次保存就是本会话产生的
        assert called["expect_mtime"] is None

    def test_rejects_unparseable_source_path(self) -> None:
        """源路径解不出案件就报错让 DS 重试，绝不猜一个目标去写。"""
        domain = get_domain("case_folder")
        assert domain is not None

        class _S:
            task_type = "case_folder"
            source_path = "/api/v1/cases/abc/unknown"
            user = None

        with pytest.raises(RuntimeError):
            domain.adopt_edited(_S(), b"x", 1)

    def test_rejects_cross_domain_source_path(self) -> None:
        """会话若是合同域的路径，案件域绝不能接住它（写错目标 = 静默写坏合同文件）。"""
        domain = get_domain("case_folder")
        assert domain is not None

        class _S:
            task_type = "case_folder"
            source_path = "/api/v1/contracts/318/folder-file?subpath=a.docx"
            user = None

        with pytest.raises(RuntimeError):
            domain.adopt_edited(_S(), b"x", 1)
