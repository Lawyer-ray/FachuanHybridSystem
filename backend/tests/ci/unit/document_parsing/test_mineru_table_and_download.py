"""MinerU 结果解析里两段"\u5939\u5c42\u903b\u8f91"\u7684\u5355\u6d4b\uff1a\u8868\u683c\u6587\u672c\u56de\u9000\u4e0e\u7ed3\u679c ZIP \u4e0b\u8f7d\u91cd\u8bd5\u94fe\u3002

\u4e3a\u4ec0\u4e48\u8fd9\u4e24\u6bb5\u503c\u5f97\u5355\u72ec\u6d4b\uff1a

1. **\u8868\u683c\u6587\u672c\u56de\u9000**\uff08``_extract_page_layout_from_content_list``\uff09:
   MinerU \u5bf9\u8868\u683c\u5757\u7ed9\u7684\u662f ``table_body``\uff08\u4e00\u6bb5 HTML\uff09\uff0c``text`` \u5f80\u5f80\u662f\u7a7a\u7684\u3002\u82e5\u4e0d\u628a HTML \u53bb\u6807\u7b7e\u5199\u56de
   ``text``\uff0c\u8868\u683c\u91cc\u7684\u6570\u5b57\uff08\u672c\u91d1\u3001\u5229\u606f\u3001\u671f\u6570\u2014\u2014\u6b63\u662f\u5f8b\u5e08\u8981\u7684\u90a3\u90e8\u5206\uff09\u5728\u6b63\u6587\u91cc\u5c31\u76f4\u63a5\u6d88\u5931\u4e86\u3002\u6ca1\u6709 ``table_body``
   \u65f6\u9000\u56de\u8868\u683c\u6807\u9898 / \u6ce8\u91ca\uff0c\u81f3\u5c11\u80fd\u544a\u8bc9\u4eba"\u8fd9\u91cc\u6709\u4e00\u5f20\u4ec0\u4e48\u8868"\u3002\u4e24\u4e2a\u5b57\u6bb5\u5728\u5b9e\u9645\u8fd4\u56de\u91cc
   **\u65e2\u53ef\u80fd\u662f str \u4e5f\u53ef\u80fd\u662f list**\uff08\u4e0d\u540c MinerU \u7248\u672c/\u6a21\u578b\uff09\uff0c\u4e24\u79cd\u5f62\u6001\u90fd\u5fc5\u987b\u5904\u7406\uff0c\u5426\u5219 ``+`` \u76f4\u63a5 TypeError\u3002

2. **\u7ed3\u679c ZIP \u4e0b\u8f7d\u91cd\u8bd5\u94fe**\uff08``_download_result_zip``\uff09\uff1a\u7ed3\u679c\u5b58\u50a8 CDN \u7ecf\u4ee3\u7406\u96a7\u9053\u5076\u53d1 TLS
   \u6376\u65ad\uff08UNEXPECTED_EOF\uff09\uff0c\u6240\u4ee5\u8bbe\u8ba1\u4e86"\u5947\u6570\u8f6e\u8d70\u73af\u5883\u9ed8\u8ba4\u4ee3\u7406\u3001\u5076\u6570\u8f6e\u76f4\u8fde"\u7684\u4ea4\u66ff\u91cd\u8bd5\u3002
   \u8fd9\u91cc\u9501\u4f4f\u7684\u662f\u91cd\u8bd5\u6b21\u6570\u4e0e\u6700\u7ec8\u5931\u8d25\u5f62\u5f0f\uff1a**\u4e2d\u95f4\u5931\u8d25\u5fc5\u987b\u91cd\u8bd5\u3001\u6700\u540e\u4e00\u6b21\u5931\u8d25\u5fc5\u987b\u628a\u539f
   ``httpx.HTTPError`` \u4e22\u51fa\u53bb**\uff08\u4e0a\u5c42 ``_parse_result_zip`` \u9760\u5b83\u533a\u5206"\u4e0b\u8f7d\u5931\u8d25"\u4e0e"\u89e3\u538b/\u89e3\u6790\u5931\u8d25"\uff09\u3002

\u6d4b\u8bd5\u6570\u636e\u5168\u90e8\u865a\u6784\uff08\u6848\u53f7\u3001\u91d1\u989d\u3001\u4eba\u540d\u5931\u91cf\u5904\u7406\uff09\u3002
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.document_parsing.services.backends.mineru_backend import MineruBackend

_PATCH_PREFIX = "apps.document_parsing.services.backends.mineru_backend"


def _make_backend() -> MineruBackend:
    with patch(f"{_PATCH_PREFIX}.get_sync_http_client"):
        return MineruBackend(api_key="test-key")  # pragma: allowlist secret


def _layout(tmp_path: Path, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """把 blocks 写成 content_list.json，走真实读取路径拿到 layout。"""
    content_list = tmp_path / "content_list.json"
    content_list.write_text(json.dumps(blocks, ensure_ascii=False), encoding="utf-8")
    return _make_backend()._extract_page_layout_from_content_list(content_list)


def _only_block(layout: dict[str, Any]) -> dict[str, Any]:
    pages = layout["pages"]
    assert len(pages) == 1
    blocks = pages[0]["blocks"]
    assert len(blocks) == 1
    return blocks[0]


class TestTableBodyFallback:
    """``type=="table"`` 且 ``table_body`` 非空 → 去 HTML 标签 + 压缩空白写进 text。"""

    def test_表格HTML被去标签成可读文本(self, tmp_path: Path) -> None:
        """表格里的金额/日期只在 HTML 里；不去标签就等于卷宗正文丢了这些数字。"""
        block = _only_block(
            _layout(
                tmp_path,
                [
                    {
                        "type": "table",
                        "text": "",
                        "table_body": "<table><tr><td>本金</td><td>10000元</td></tr>"
                        "<tr><td>利息</td><td>500元</td></tr></table>",
                        "page_idx": 0,
                    }
                ],
            )
        )

        assert "本金" in block["text"] and "10000元" in block["text"]
        assert "<table>" not in block["text"], "标签必须清掉，否则正文里全是尖括号"
        # 标签被替换成空格再压缩空白：不会把相邻单元格黏成「本金10000元」
        assert "本金 10000元" in block["text"]
        # 原始 HTML 作为结构化数据保留在 table_body 里，供需要合并单元格的下游用
        assert block["table_body"].startswith("<table>")

    def test_HTML实体被反转义(self, tmp_path: Path) -> None:
        """MinerU 会输出 ``&amp;`` / ``&lt;`` 之类实体；不反转义律师看到的是乱码。"""
        block = _only_block(
            _layout(
                tmp_path,
                [
                    {
                        "type": "table",
                        "text": "",
                        "table_body": "<table><tr><td>甲方&amp;乙方</td><td>3&lt;5</td></tr></table>",
                        "page_idx": 0,
                    }
                ],
            )
        )

        assert "甲方&乙方" in block["text"]
        assert "3<5" in block["text"]

    def test_连续空白被压成单个空格(self, tmp_path: Path) -> None:
        """表格 HTML 常带大量换行与缩进；不压缩会让正文里出现大段空白。"""
        block = _only_block(
            _layout(
                tmp_path,
                [
                    {
                        "type": "table",
                        "text": "",
                        "table_body": "<table>\n\n   <tr>\n      <td>合计\n\n   </td>\n   </tr></table>",
                        "page_idx": 0,
                    }
                ],
            )
        )

        assert block["text"] == "合计"
        assert "\n" not in block["text"]

    def test_非表格块不受table_body影响(self, tmp_path: Path) -> None:
        """``table_body`` 出现在非 table 块上（脏数据）时，普通文本必须原样保留。"""
        block = _only_block(
            _layout(
                tmp_path,
                [{"type": "text", "text": "正文内容", "table_body": "<b>不该覆盖我</b>", "page_idx": 0}],
            )
        )

        assert block["text"] == "正文内容"

    def test_table_body为空时不覆盖已有text(self, tmp_path: Path) -> None:
        block = _only_block(_layout(tmp_path, [{"type": "table", "text": "表格", "table_body": "", "page_idx": 0}]))

        assert block["text"] == "表格"


class TestTableCaptionFallback:
    """``block_text`` 为空时用 ``table_caption`` / ``table_footnote`` 拼接。

    没有 table_body 的表格（纯图片表、被裁剪的表）至少要把标题与注释保留下来，
    否则这一整页在正文里就是一个空洞——律师根本不知道这里原本有张表。
    """

    def test_str形态的标题与注释被拼接(self, tmp_path: Path) -> None:
        """老版本 MinerU 返回单字符串。"""
        block = _only_block(
            _layout(
                tmp_path,
                [
                    {
                        "type": "table",
                        "text": "",
                        "table_caption": "表一：借款明细",
                        "table_footnote": "注：金额单位为元",
                        "page_idx": 0,
                    }
                ],
            )
        )

        assert block["text"] == "表一：借款明细 注：金额单位为元"

    def test_list形态的标题与注释被拼接(self, tmp_path: Path) -> None:
        """新版本返回字符串数组；直接 ``+`` 会 TypeError，必须先归一成 list。"""
        block = _only_block(
            _layout(
                tmp_path,
                [
                    {
                        "type": "table",
                        "text": "",
                        "table_caption": ["表一：借款明细", "（续）"],
                        "table_footnote": ["注：金额单位为元", "注：日期为签订日"],
                        "page_idx": 0,
                    }
                ],
            )
        )

        assert block["text"] == "表一：借款明细 （续） 注：金额单位为元 注：日期为签订日"

    def test_只有标题时也能回退(self, tmp_path: Path) -> None:
        block = _only_block(
            _layout(tmp_path, [{"type": "table", "text": "", "table_caption": ["仅标题"], "page_idx": 0}])
        )

        assert block["text"] == "仅标题"

    def test_只有注释时也能回退(self, tmp_path: Path) -> None:
        block = _only_block(
            _layout(tmp_path, [{"type": "table", "text": "", "table_footnote": "仅注释", "page_idx": 0}])
        )

        assert block["text"] == "仅注释"

    def test_空字符串条目被过滤(self, tmp_path: Path) -> None:
        """数组里常混空串；不过滤会拼出多余空格，前端胶囊里看着像空白标题。"""
        block = _only_block(
            _layout(
                tmp_path,
                [
                    {
                        "type": "table",
                        "text": "",
                        "table_caption": ["", "表二：还款计划", "   "],
                        "table_footnote": [],
                        "page_idx": 0,
                    }
                ],
            )
        )

        assert block["text"] == "表二：还款计划"

    def test_text非空时不使用标题覆盖(self, tmp_path: Path) -> None:
        """已有正文就不要再拿标题顶替——那会把真实内容换成"表一：xxx"。"""
        block = _only_block(
            _layout(
                tmp_path,
                [{"type": "table", "text": "真实内容", "table_caption": "表一：标题", "page_idx": 0}],
            )
        )

        assert block["text"] == "真实内容"

    def test_回退文本会进入页面正文(self, tmp_path: Path) -> None:
        """回退结果必须真的并进 ``page["text"]``，否则等于白回退。"""
        layout = _layout(
            tmp_path,
            [{"type": "table", "text": "", "table_caption": ["表一：借款明细"], "page_idx": 0}],
        )

        assert "表一：借款明细" in layout["pages"][0]["text"]

    def test_页眉页脚类型的回退文本不并入正文(self, tmp_path: Path) -> None:
        """header/footer/page_number 不进正文——否则每页都重复一遍页眉，正文全是噪音。

        这条与表格回退共用同一段 ``if block_type not in {...}`` 判断，所以一起锁住。
        """
        layout = _layout(
            tmp_path,
            [
                {"type": "header", "text": "", "table_caption": ["某某法院"], "page_idx": 0},
                {"type": "page_number", "text": "第 3 页", "page_idx": 0},
            ],
        )
        page = layout["pages"][0]
        assert page["text"] == ""
        assert page["blocks"][0]["text"] == "某某法院", "块自身仍保留文本，只是不并入正文"


class TestDownloadResultZipRetry:
    """``_download_result_zip`` 的重试链。

    设计（见源码 docstring）：奇数轮 ``trust_env=True``（走环境代理），偶数轮直连。
    结果存储 CDN 经代理隧道偶发 TLS 掐断，直连能绕过；必须经代理出网的环境则由
    奇数轮承担。两路交替保证至少各试一次。
    """

    @staticmethod
    def _client_class(*responses: Any) -> MagicMock:
        """构造 ``httpx.Client`` 替身：第 N 次 ``with`` 进入拿到第 N 个响应/异常。

        注意 ``with httpx.Client(...) as c`` 取的是 ``__enter__``，所以按实例走
        ``side_effect`` 是不生效的——必须在 ``__enter__`` 上按调用次序发牌。
        """
        client_cls = MagicMock()

        def _enter(*_args: Any) -> Any:
            item = responses[client_cls.call_count - 1]
            client = MagicMock()
            if isinstance(item, Exception):
                client.stream.side_effect = item
            else:
                client.stream.return_value.__enter__.return_value = item
            return client

        client_cls.return_value.__enter__.side_effect = _enter
        return client_cls

    def test_中途失败后重试成功(self, tmp_path: Path) -> None:
        """CDN 掐断一次不该让整次解析失败：必须 warn + sleep + 重试。"""
        backend = _make_backend()
        ok = MagicMock()
        ok.iter_bytes.return_value = [b"zip-payload"]
        client_cls = self._client_class(httpx.ConnectError("tls eof"), ok)
        zip_path = tmp_path / "result.zip"

        with (
            patch(f"{_PATCH_PREFIX}.httpx.Client", client_cls),
            patch(f"{_PATCH_PREFIX}.time.sleep") as sleep,
        ):
            backend._download_result_zip("https://example.com/result.zip", zip_path)

        assert zip_path.read_bytes() == b"zip-payload"
        assert client_cls.call_count == 2, "第一次失败后必须再试一次"
        sleep.assert_called_once_with(1), "重试间隔按第几次尝试递增（这里是第 1 次）"

    def test_重试轮换绕过代理(self, tmp_path: Path) -> None:
        """奇偶轮必须交替 trust_env——两轮都走代理就绕不过那个 TLS 掐断。"""
        backend = _make_backend()
        ok = MagicMock()
        ok.iter_bytes.return_value = [b"x"]
        client_cls = self._client_class(httpx.ConnectError("boom"), ok)

        with (
            patch(f"{_PATCH_PREFIX}.httpx.Client", client_cls),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
        ):
            backend._download_result_zip("https://example.com/result.zip", tmp_path / "r.zip")

        trust_env = [call.kwargs["trust_env"] for call in client_cls.call_args_list]
        assert trust_env == [True, False], "奇数轮走环境代理，偶数轮直连"

    def test_最后一次仍失败时把原始异常抛出去(self, tmp_path: Path) -> None:
        """最后一次不再吞异常：上层 ``_parse_result_zip`` 靠它区分下载失败与解析失败。"""
        backend = _make_backend()
        calls = backend.RESULT_DOWNLOAD_ATTEMPTS
        client_cls = self._client_class(*[httpx.ReadTimeout("still down") for _ in range(calls)])

        with (
            patch(f"{_PATCH_PREFIX}.httpx.Client", client_cls),
            patch(f"{_PATCH_PREFIX}.time.sleep") as sleep,
        ):
            with pytest.raises(httpx.ReadTimeout):
                backend._download_result_zip("https://example.com/result.zip", tmp_path / "r.zip")

        assert client_cls.call_count == calls, "必须用满重试次数才放弃"
        assert sleep.call_count == calls - 1, "最后一次失败后不再 sleep（马上要抛）"

    def test_重试耗尽不会写出半截文件(self, tmp_path: Path) -> None:
        """每次重试都重新打开 ``wb``；失败的那几轮不能留下可被误读的残文件。"""
        backend = _make_backend()
        client_cls = self._client_class(*[httpx.ConnectError("down") for _ in range(backend.RESULT_DOWNLOAD_ATTEMPTS)])
        zip_path = tmp_path / "result.zip"

        with (
            patch(f"{_PATCH_PREFIX}.httpx.Client", client_cls),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
        ):
            with pytest.raises(httpx.ConnectError):
                backend._download_result_zip("https://example.com/result.zip", zip_path)

        assert not zip_path.exists()
