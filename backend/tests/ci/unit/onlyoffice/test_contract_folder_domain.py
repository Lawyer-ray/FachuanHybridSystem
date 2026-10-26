"""contract_folder 业务域：让 OnlyOffice 能直接预览合同文件夹里的文件。

**为什么需要**：以前文件夹里的 docx 点开只能下载——浏览器没有 docx 渲染器，
`window.open` 必然落到本地磁盘。要让律师直接看到内容，DS 必须能拉到这个
文件，而 DS 容器带不上 Authorization，只能走 `/onlyoffice/file?src=&sig=`
代理，代理只放行注册表里注册过的路径。

重点：
- 路径能解析出 contract_id + subpath；
- 取文件走原端点的 ACL（代理不能比 REST 宽松）；
- 不接保存回写（预览里改的东西不落盘，落盘要走审查链路）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apps.onlyoffice.services.domain_registry import domain_for_path, get_domain


class TestContractFolderPath:
    def test_registered(self) -> None:
        assert get_domain("contract_folder") is not None

    def test_parses_contract_and_subpath(self) -> None:
        hit = domain_for_path("/api/v1/contracts/318/folder-file?subpath=1-%E5%90%88%E5%90%8C/a.docx")
        assert hit is not None
        domain, contract_id, subpath = hit
        assert domain.key == "contract_folder"
        assert contract_id == 318
        # Django 解析 query 时已解码一次，这里拿到的是解码后的原文
        assert subpath == "1-%E5%90%88%E5%90%8C/a.docx"

    def test_subpath_with_extra_query_params(self) -> None:
        """下载票据会追加 &ticket=…，subpath 之后还有参数也必须能解析。"""
        hit = domain_for_path("/api/v1/contracts/7/folder-file?subpath=x.docx&ticket=abc123")
        assert hit is not None
        assert hit[1] == 7
        assert hit[2] == "x.docx"

    def test_does_not_swallow_contract_review_paths(self) -> None:
        """两个域的正则不能互相抢：review 路径必须仍归 contract_review。"""
        hit = domain_for_path("/api/v1/contract-review/6f1e0000-0000-0000-0000-000000000000/download")
        assert hit is not None
        assert hit[0].key == "contract_review"


class TestContractFolderFileResolution:
    """取文件必须沿用原端点 ACL，代理不能放宽权限。"""

    @pytest.mark.django_db
    def test_unauthorized_user_gets_none(self, monkeypatch: Any) -> None:
        """ACL 拒绝时返回 None（对 DS 表现为 404，不是 500 无限重试）。"""
        domain = get_domain("contract_folder")
        assert domain is not None and domain.resolve_for_proxy is not None

        class Denied(Exception):
            pass

        def boom(_self: Any, **_kw: Any) -> Any:
            raise Denied("无权访问")

        from apps.contracts.services.contract.integrations import folder_browse_service as mod

        monkeypatch.setattr(mod.ContractFolderBrowseService, "resolve_file", boom, raising=False)

        out = domain.resolve_for_proxy(object(), 318, "a.docx")
        assert out is None

    @pytest.mark.django_db
    def test_returns_path_when_allowed(self, monkeypatch: Any, tmp_path: Path) -> None:
        domain = get_domain("contract_folder")
        assert domain is not None and domain.resolve_for_proxy is not None

        f = tmp_path / "a.docx"
        f.write_bytes(b"PK\x03\x04")

        from apps.contracts.services.contract.integrations import folder_browse_service as mod

        monkeypatch.setattr(mod.ContractFolderBrowseService, "resolve_file", lambda _self, **_kw: f, raising=False)
        assert domain.resolve_for_proxy(object(), 318, "a.docx") == f


class TestSaveWriteback:
    """决定「原地改、原地存」后，回写必须真的覆写原文件。"""

    @pytest.mark.django_db
    def test_adopt_edited_writes_back_to_source_file(self, monkeypatch: Any, tmp_path: Path) -> None:
        """从 session.source_path 反解 contract + subpath，覆写那一份。"""
        domain = get_domain("contract_folder")
        assert domain is not None

        called: dict[str, Any] = {}

        def fake_save(_self: Any, **kw: Any) -> dict[str, Any]:
            called.update(kw)
            return {"subpath": kw["subpath"], "name": "a.docx", "size": len(kw["data"])}

        from apps.contracts.services.contract.integrations import folder_browse_service as mod

        monkeypatch.setattr(mod.ContractFolderBrowseService, "save_file_content", fake_save, raising=False)

        class _S:
            task_type = "contract_folder"
            # 真实会话里 source_path 就是当初打开的站内路径（subpath 已 urlencode）
            source_path = "/api/v1/contracts/318/folder-file?subpath=1-%E5%90%88%E5%90%8C/a.docx"
            user = None

        domain.adopt_edited(_S(), b"newbytes", 1)

        assert called["owner_id"] == 318
        # 双层编码要解开，否则写到一个名字带 % 的错位置
        assert called["subpath"] == "1-合同/a.docx"
        assert called["data"] == b"newbytes"
        # 回写不校验 mtime：这次保存就是本会话产生的
        assert called["expect_mtime"] is None

    def test_rejects_unparseable_source_path(self) -> None:
        """源路径解不出契约就报错让 DS 重试，绝不猜一个目标去写。"""
        domain = get_domain("contract_folder")
        assert domain is not None

        class _S:
            task_type = "contract_folder"
            source_path = "/api/v1/contracts/abc/unknown"
            user = None

        with pytest.raises(RuntimeError):
            domain.adopt_edited(_S(), b"x", 1)
