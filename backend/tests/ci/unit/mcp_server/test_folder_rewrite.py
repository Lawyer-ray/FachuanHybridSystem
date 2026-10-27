"""rewrite_folder_file 的合同/案件二选一分流（MCP 工具参数面）。

**为什么锁这个**：案件接入前工具显式拒绝 case_id；现在两个 id 都收，最大的
风险变成「模型把引用块读串，case_id 当 contract_id 发（或反之）」——后端会
写进**同编号的另一份合同/案件**，静默写坏。用例守住：

- 二选一硬校验（都给 / 都不给 ValueError，不发请求）；
- 只给 case_id 时 payload 落 case_id 键、**绝不携带 contract_id**；
- 只给 contract_id 时保持存量形状（合同直改回归）。
"""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest


@pytest.fixture()
def fake_client() -> Any:
    from mcp_server.tools.contracts import folder_rewrite

    shared = mock.MagicMock()
    shared.post.return_value = {"applied": True, "subpath": "a.docx", "name": "a.docx", "reason": ""}
    with mock.patch.object(folder_rewrite, "client", shared):
        yield shared


class TestRewriteFolderFileDispatch:
    def test_case_id_only_sends_case_key(self, fake_client: Any) -> None:
        from mcp_server.tools.contracts.folder_rewrite import rewrite_folder_file

        out = rewrite_folder_file(
            subpath="2-诉状/起诉状.docx",
            original="请求判令被告支付货款",
            replacement="请求判令被告立即支付全部货款",
            case_id=399,
        )
        assert out["applied"] is True
        _path, kwargs = fake_client.post.call_args
        payload = kwargs["json"]
        assert payload["case_id"] == 399
        # 反向键绝不出现：case_id 被当 contract_id 发出去就是写错文件
        assert "contract_id" not in payload
        assert payload["selection"] == "请求判令被告支付货款"
        assert payload["suggested"] == "请求判令被告立即支付全部货款"

    def test_contract_id_only_keeps_legacy_shape(self, fake_client: Any) -> None:
        from mcp_server.tools.contracts.folder_rewrite import rewrite_folder_file

        rewrite_folder_file(
            subpath="1-合同/a.docx",
            original="旧文本",
            replacement="新文本",
            contract_id=318,
        )
        _path, kwargs = fake_client.post.call_args
        payload = kwargs["json"]
        assert payload["contract_id"] == 318
        assert "case_id" not in payload

    def test_both_ids_rejected_without_request(self, fake_client: Any) -> None:
        from mcp_server.tools.contracts.folder_rewrite import rewrite_folder_file

        with pytest.raises(ValueError, match="二选一"):
            rewrite_folder_file(subpath="a.docx", original="x", replacement="y", contract_id=1, case_id=2)
        fake_client.post.assert_not_called()

    def test_neither_id_rejected_without_request(self, fake_client: Any) -> None:
        from mcp_server.tools.contracts.folder_rewrite import rewrite_folder_file

        with pytest.raises(ValueError, match="二选一"):
            rewrite_folder_file(subpath="a.docx", original="x", replacement="y")
        fake_client.post.assert_not_called()

    def test_non_positive_id_rejected(self, fake_client: Any) -> None:
        from mcp_server.tools.contracts.folder_rewrite import rewrite_folder_file

        with pytest.raises(ValueError, match="case_id"):
            rewrite_folder_file(subpath="a.docx", original="x", replacement="y", case_id=0)
        fake_client.post.assert_not_called()
