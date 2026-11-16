"""MineruBackend 测试（核心 — mock httpx）"""

import json
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.document_parsing.exceptions import MineruAPIError, ParsingTimeoutError
from apps.document_parsing.protocols.document_parser_protocol import ParsedDocument, TextExtractionResult
from apps.document_parsing.services.backends import mineru_backend
from apps.document_parsing.services.backends.mineru_backend import MineruBackend


def _mock_upload_client(put_response=None):
    """构造 _put_file_streaming 用的独立 httpx.Client 替身。

    上传现在走**独立客户端**（不是共享工厂）：要按文件体积单独设超时，还要在
    重试轮换 trust_env。所以测试必须同时 patch `httpx.Client`，否则 PUT 会打真网。
    """
    client = MagicMock()
    client.put.return_value = put_response if put_response is not None else _mock_response(200)
    ctx = MagicMock()
    ctx.__enter__.return_value = client
    ctx.__exit__.return_value = False
    return ctx, client


_PATCH_PREFIX = "apps.document_parsing.services.backends.mineru_backend"


def _mock_response(status_code: int = 200, json_data: dict | None = None, content: bytes = b""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.content = content
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx

        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


def _mock_stream_response(status_code: int = 200, content: bytes = b""):
    """构造 httpx 流式响应替身（iter_bytes 分块产出 content）。"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.iter_bytes.return_value = [content]
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx

        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


def _make_backend(api_key: str = "test-key") -> MineruBackend:
    with patch(f"{_PATCH_PREFIX}.get_sync_http_client"):
        return MineruBackend(api_key=api_key)


def _make_zip_bytes(files: dict[str, str]) -> bytes:
    """创建包含指定文件的 ZIP bytes。files: {filename: content}"""
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@contextmanager
def _patch_http(mock_client, content: bytes = b""):
    """同时 patch API 客户端工厂与结果 ZIP 流式下载所用的独立 ``httpx.Client``。

    ``_download_result_zip`` 的结果下载刻意每次新建连接池 + ``client.stream``
    流式写盘（规避对象存储关闭的 TLS keep-alive 连接），因此**不走**
    ``get_sync_http_client``。若不一并 patch，测试会真实请求
    ``https://example.com/result.zip`` 并拿到 404。
    """
    client_cls = MagicMock()
    client_cls.return_value.__enter__.return_value = mock_client
    mock_client.stream.return_value.__enter__.return_value = _mock_stream_response(content=content)
    with (
        patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client),
        patch(f"{_PATCH_PREFIX}.httpx.Client", client_cls),
    ):
        yield mock_client


# ── __init__ ─────────────────────────────────────────────────────


def _mock_provider(creds: list[str], concurrency: int = 3, name: str = "MinerU"):
    provider = MagicMock()
    provider.name = name
    provider.parsed_credentials.return_value = creds
    provider.concurrency_per_key = concurrency
    return provider


class TestInit:
    def test_api_key_from_param(self) -> None:
        with patch(f"{_PATCH_PREFIX}.get_sync_http_client"):
            backend = MineruBackend(api_key="my-key")  # pragma: allowlist secret
        assert backend.api_key == "my-key"  # pragma: allowlist secret

    def test_api_key_from_config(self) -> None:
        with (
            patch(f"{_PATCH_PREFIX}.get_sync_http_client"),
            patch(
                "apps.core.services.document_parse_provider_service.ParseProviderService.get_provider",
                return_value=_mock_provider(["cfg-key-1", "cfg-key-2"]),
            ),
        ):
            backend = MineruBackend()
        assert backend.api_key == "cfg-key-1"  # pragma: allowlist secret
        assert len(backend._pool.credentials) == 2

    def test_no_provider_raises(self) -> None:
        with (
            patch(f"{_PATCH_PREFIX}.get_sync_http_client"),
            patch(
                "apps.core.services.document_parse_provider_service.ParseProviderService.get_provider",
                return_value=None,
            ),
        ):
            with pytest.raises(ValueError, match="未配置 MinerU 解析平台"):
                MineruBackend()

    def test_provider_no_credentials_raises(self) -> None:
        with (
            patch(f"{_PATCH_PREFIX}.get_sync_http_client"),
            patch(
                "apps.core.services.document_parse_provider_service.ParseProviderService.get_provider",
                return_value=_mock_provider([]),
            ),
        ):
            with pytest.raises(ValueError, match="未填写凭证"):
                MineruBackend()

    def test_custom_timeout(self) -> None:
        with patch(f"{_PATCH_PREFIX}.get_sync_http_client"):
            backend = MineruBackend(api_key="k", timeout=60)
        assert backend.timeout == 60


# ── get_supported_formats ────────────────────────────────────────


class TestGetSupportedFormats:
    def test_returns_all_formats(self) -> None:
        backend = _make_backend()
        fmts = backend.get_supported_formats()
        assert "pdf" in fmts
        assert "docx" in fmts
        assert "jpg" in fmts
        assert len(fmts) >= 10


# ── _upload_file ─────────────────────────────────────────────────


class TestUploadFile:
    def test_success(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_client = MagicMock()

        batch_resp = _mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "batch_id": "batch-123",
                    "file_urls": ["https://oss.example.com/upload?sig=abc"],
                },
            },
        )
        mock_client.post.return_value = batch_resp
        upload_ctx, upload_client = _mock_upload_client()

        with (
            patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client),
            patch(f"{_PATCH_PREFIX}.httpx.Client", return_value=upload_ctx),
        ):
            batch_id = backend._upload_file(str(pdf))

        assert batch_id == "batch-123"
        mock_client.post.assert_called_once()
        # 文件本体走独立客户端流式 PUT（不整包进内存）
        upload_client.put.assert_called_once()

    def test_batch_api_error_code(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_response(
            200,
            {
                "code": -10002,
                "msg": "field missing",
            },
        )

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            with pytest.raises(MineruAPIError, match="获取上传 URL 失败"):
                backend._upload_file(str(pdf))

    def test_empty_file_urls(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_response(
            200,
            {
                "code": 0,
                "data": {"batch_id": "b1", "file_urls": []},
            },
        )

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            with pytest.raises(MineruAPIError, match="未获取到上传 URL"):
                backend._upload_file(str(pdf))

    def test_http_error(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_client = MagicMock()
        import httpx

        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            with pytest.raises(MineruAPIError, match="HTTP 请求失败"):
                backend._upload_file(str(pdf))


# ── _poll_batch_result ───────────────────────────────────────────


class TestPollBatchResult:
    """轮询结果的解析与超时控制。

    ⚠️ 轮询现在**每次新建** `httpx.Client`（不再复用共享工厂客户端）——
    共享客户端的长连接经历一次 SSL 断连后会处于半死状态，而「复用半死连接」
    正是 2026-11-16 那次 164 页全量跑 72 分钟的土壤。
    所以这些用例必须 patch `httpx.Client` 而不是 `get_sync_http_client`。
    """

    @staticmethod
    def _patch_client(mock_client):
        """把 `httpx.Client(...)` 换成 context manager，返回给定的 mock。"""
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_client
        ctx.__exit__.return_value = False
        return patch(f"{_PATCH_PREFIX}.httpx.Client", return_value=ctx)

    def test_done_immediately(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "state": "done",
                            "full_zip_url": "https://example.com/result.zip",
                            "file_name": "test.pdf",
                        }
                    ],
                },
            },
        )

        with (
            self._patch_client(mock_client),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
        ):
            result = backend._poll_batch_result("batch-123")

        assert result["state"] == "done"
        assert result["full_zip_url"] == "https://example.com/result.zip"

    def test_failed_state(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "state": "failed",
                            "err_msg": "corrupted file",
                        }
                    ],
                },
            },
        )

        with (
            self._patch_client(mock_client),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
        ):
            with pytest.raises(MineruAPIError, match="corrupted file"):
                backend._poll_batch_result("batch-123")

    def test_waiting_then_done(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock()
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_response(
                    200,
                    {
                        "code": 0,
                        "data": {"extract_result": []},
                    },
                )
            return _mock_response(
                200,
                {
                    "code": 0,
                    "data": {
                        "extract_result": [
                            {
                                "state": "done",
                                "full_zip_url": "https://example.com/result.zip",
                            }
                        ],
                    },
                },
            )

        mock_client.get.side_effect = side_effect

        with (
            self._patch_client(mock_client),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
        ):
            result = backend._poll_batch_result("batch-123")

        assert result["state"] == "done"
        assert call_count == 2

    def test_api_error_code(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(
            200,
            {
                "code": -10002,
                "msg": "not found",
            },
        )

        with (
            self._patch_client(mock_client),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
        ):
            with pytest.raises(MineruAPIError, match="查询结果失败"):
                backend._poll_batch_result("batch-123")

    def test_http_error_retries(self) -> None:
        import httpx

        backend = _make_backend()
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("timeout")
            return _mock_response(
                200,
                {
                    "code": 0,
                    "data": {
                        "extract_result": [
                            {
                                "state": "done",
                                "full_zip_url": "https://example.com/result.zip",
                            }
                        ],
                    },
                },
            )

        mock_client = MagicMock()
        mock_client.get.side_effect = side_effect

        with (
            self._patch_client(mock_client),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
        ):
            result = backend._poll_batch_result("batch-123")

        assert result["state"] == "done"
        assert call_count == 2

    def test_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = _make_backend()
        backend.POLL_TIMEOUT = 0  # 立即超时

        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(
            200,
            {
                "code": 0,
                "data": {"extract_result": [{"state": "running"}]},
            },
        )

        import time as time_mod

        original_time = time_mod.time
        # 让 elapsed 始终大于 POLL_TIMEOUT
        monkeypatch.setattr(f"{_PATCH_PREFIX}.time.time", lambda: original_time() + 999)
        monkeypatch.setattr(f"{_PATCH_PREFIX}.time.sleep", lambda _: None)

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            with pytest.raises(ParsingTimeoutError, match="超时"):
                backend._poll_batch_result("batch-123")


# ── _parse_result_zip ────────────────────────────────────────────


def _layout_json_sample() -> str:
    """按实测 MinerU SaaS 结果形状构造 layout.json（page_size + preproc_blocks）。

    文本块的 lines/spans 直接挂在块上；表格块没有 lines，只有子块 ``table_body``
    里的整表 line + ``span.html``——与真实返回一致。
    """
    return json.dumps(
        {
            "pdf_info": [
                {
                    "page_idx": 0,
                    "page_size": [612, 1008],
                    "preproc_blocks": [
                        {
                            "type": "text",
                            "bbox": [128, 90, 408, 119],
                            "lines": [
                                {
                                    "bbox": [128, 90, 408, 119],
                                    "spans": [{"bbox": [128, 90, 408, 119], "type": "text", "content": "地址：某某路"}],
                                }
                            ],
                        },
                        {
                            "type": "table",
                            "bbox": [22, 89, 600, 744],
                            "blocks": [
                                {
                                    "type": "table_body",
                                    "bbox": [22, 89, 600, 744],
                                    "lines": [
                                        {
                                            "bbox": [22, 89, 600, 744],
                                            "spans": [
                                                {
                                                    "bbox": [22, 89, 600, 744],
                                                    "type": "table",
                                                    "html": "<table><tr><td>1</td></tr></table>",
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                    "discarded_blocks": [],
                }
            ]
        }
    )


def _model_json_sample() -> str:
    """按实测 MinerU SaaS 结果形状构造 model.json（二维数组：外层页、内层元素）。

    bbox 是**归一化 0-1**（与 content_list 的千分比不同口径），``text`` 恒为空、
    ``score`` 恒为 1.0——与真实返回一致，用来验证只靠坐标、不靠文本匹配。
    第 2 页是表格页，实测 0 个 ocr_text。
    """
    return json.dumps(
        [
            [
                {"type": "text", "bbox": [0.209, 0.089, 0.666, 0.118], "text": "地址：某某路 电话：123"},
                {"type": "text", "bbox": [0.148, 0.237, 0.813, 0.289], "text": "兹证明某某老师…"},
                {"type": "text", "bbox": [0.519, 0.63, 0.715, 0.687], "text": "已核对与原件相符\n经办人：某某"},
                {"type": "header", "bbox": [0.212, 0.034, 0.769, 0.087], "text": "页眉"},
                # 以下 ocr_text 都在数组末尾（实测如此），只给坐标
                #
                # 地址块：content 写成一整行（无 \n），但 ocr_text 给了两个**y 区间重叠**的
                # 框（88-110 与 102-119）。它们不是两行，是同一行的重叠检测。
                # 同理「1 行 vs 2 框」→ 按红线放弃，不挂 line_boxes。
                {"type": "ocr_text", "bbox": [0.209, 0.088, 0.666, 0.11], "text": "", "score": 1.0},
                {"type": "ocr_text", "bbox": [0.21, 0.102, 0.395, 0.119], "text": "", "score": 1.0},
                # 兹证明块：content 1 行但 ocr_text 2 框（长文本折行），必须放弃。
                # 两框都落在块 y 范围内（否则第二个会被 y 过滤掉，测不到红线）
                {"type": "ocr_text", "bbox": [0.149, 0.24, 0.656, 0.262], "text": "", "score": 1.0},
                {"type": "ocr_text", "bbox": [0.148, 0.265, 0.813, 0.288], "text": "", "score": 1.0},
                # 已核对块：2 行 2 框，但故意倒序存放，验证按 y 升序还原阅读顺序
                {"type": "ocr_text", "bbox": [0.521, 0.666, 0.715, 0.687], "text": "", "score": 1.0},
                {"type": "ocr_text", "bbox": [0.519, 0.63, 0.716, 0.652], "text": "", "score": 1.0},
            ],
            [
                {"type": "header", "bbox": [0.741, 0.026, 0.834, 0.045], "text": "000040"},
                {"type": "table", "bbox": [0.035, 0.088, 0.98, 0.738], "text": "表格"},
            ],
        ]
    )


def _content_list_with_text_blocks() -> str:
    """与 ``_model_json_sample`` 同页同块的 content_list.json（千分比坐标）。"""
    return json.dumps(
        [
            {"type": "text", "text": "地址：某某路 电话：123", "bbox": [209, 89, 666, 118], "page_idx": 0},
            {"type": "text", "text": "兹证明某某老师…", "bbox": [148, 237, 813, 289], "page_idx": 0},
            {"type": "text", "text": "已核对与原件相符\n经办人：某某", "bbox": [519, 630, 715, 687], "page_idx": 0},
            {"type": "header", "text": "页眉", "bbox": [212, 34, 769, 87], "page_idx": 0},
            {"type": "header", "text": "000040", "bbox": [741, 26, 834, 45], "page_idx": 1},
            {"type": "table", "text": "表格", "bbox": [35, 88, 980, 738], "page_idx": 1},
        ]
    )


class TestParseResultZip:
    def test_with_content_list_json(self) -> None:
        backend = _make_backend()
        zip_bytes = _make_zip_bytes(
            {
                "result/test_content_list.json": json.dumps(
                    [
                        {"type": "text", "text": "第一段"},
                        {"type": "table", "text": "表格数据"},
                        {"type": "text", "text": "第二段"},
                    ]
                ),
                "result/output.md": "# 标题\n\n正文",
            }
        )

        mock_client = MagicMock()

        with _patch_http(mock_client, content=zip_bytes):
            result = backend._parse_result_zip("https://example.com/result.zip")

        assert isinstance(result, ParsedDocument)
        assert "第一段" in result.text
        assert "第二段" in result.text
        assert result.parse_method == "mineru"

    def test_layout_json_adds_page_size_and_lines(self) -> None:
        """layout.json 补上 content_list 缺的页面尺寸与行级 box；表格块行级信息保持为空。"""
        backend = _make_backend()
        zip_bytes = _make_zip_bytes(
            {
                "result/test_content_list.json": json.dumps(
                    [
                        {"type": "text", "text": "地址：某某路", "bbox": [209, 89, 666, 118], "page_idx": 0},
                        {"type": "table", "text": "1", "bbox": [35, 88, 980, 738], "page_idx": 0},
                        # content_list 独有的页眉块（layout.json 放在 discarded_blocks），不参与对齐
                        {"type": "header", "text": "页眉", "bbox": [212, 34, 769, 87], "page_idx": 0},
                    ]
                ),
                "result/layout.json": _layout_json_sample(),
                "result/output.md": "地址：某某路",
            }
        )

        with _patch_http(MagicMock(), content=zip_bytes):
            result = backend._parse_result_zip("https://example.com/result.zip")

        assert result.layout is not None
        page = result.layout["pages"][0]
        assert page["width"] == 612
        assert page["height"] == 1008

        text_block, table_block, header_block = page["blocks"]
        assert text_block["lines"][0]["bbox"] == [128, 90, 408, 119]
        assert text_block["lines"][0]["spans"][0]["content"] == "地址：某某路"
        # 表格只有整表 bbox：不把整块 box 冒充行级坐标，html 照常保留
        assert table_block["lines"] == []
        assert table_block["html"].startswith("<table>")
        # 页眉块不消耗 layout.json 的块游标，也不带 lines
        assert "lines" not in header_block

    def test_missing_layout_json_degrades_to_content_list(self) -> None:
        """没有 layout.json 时退回原行为：无页面尺寸、无行级信息，主链路文本照常。"""
        backend = _make_backend()
        zip_bytes = _make_zip_bytes(
            {
                "result/test_content_list.json": json.dumps(
                    [{"type": "text", "text": "第一段", "bbox": [209, 89, 666, 118], "page_idx": 0}]
                ),
                "result/output.md": "第一段",
            }
        )

        with _patch_http(MagicMock(), content=zip_bytes):
            result = backend._parse_result_zip("https://example.com/result.zip")

        assert "第一段" in result.text
        page = result.layout["pages"][0]
        assert "width" not in page
        assert "lines" not in page["blocks"][0]

    def test_broken_layout_json_degrades_to_content_list(self) -> None:
        """layout.json 损坏时不能拖垮整次解析，只丢行级增强信息。"""
        backend = _make_backend()
        zip_bytes = _make_zip_bytes(
            {
                "result/test_content_list.json": json.dumps(
                    [{"type": "text", "text": "第一段", "bbox": [209, 89, 666, 118], "page_idx": 0}]
                ),
                "result/layout.json": "not json!!!",
                "result/output.md": "第一段",
            }
        )

        with _patch_http(MagicMock(), content=zip_bytes):
            result = backend._parse_result_zip("https://example.com/result.zip")

        assert "第一段" in result.text
        assert "width" not in result.layout["pages"][0]

    def test_model_json_attaches_line_boxes_only_when_count_matches(self) -> None:
        """model.json 的 ocr_text 逐行框：框数=行数才挂，不等就放弃（不编造坐标）。"""
        backend = _make_backend()
        zip_bytes = _make_zip_bytes(
            {
                "result/test_content_list.json": _content_list_with_text_blocks(),
                "result/test_model.json": _model_json_sample(),
                "result/output.md": "地址：某某路 电话：123",
            }
        )

        with _patch_http(MagicMock(), content=zip_bytes):
            result = backend._parse_result_zip("https://example.com/result.zip")

        page_one, page_two = result.layout["pages"]
        address_block, long_block, checked_block, header_block = page_one["blocks"]

        # 红线：**框数 != 行数一律放弃**。地址块 content 是 1 行、ocr_text 是 2 框
        # （且两框 y 区间重叠，本就是同一行的重复检测），不能硬配成「两行」。
        # 这条与 long_block 同一口径——两者的差别只在文本长短，规则上不是两种情形。
        assert "line_boxes" not in address_block
        # 框数(2) != 行数(1)：放弃，不带字段
        assert "line_boxes" not in long_block
        # 唯一框数==行数（2 行 2 框）的块：挂上，且倒序存放的 ocr_text
        # 按 y 升序还原成阅读顺序
        assert [line["bbox"][1] for line in checked_block["line_boxes"]] == [630, 666]
        # 页眉不让 ocr_text 消化（实测 ocr_text 不含页眉）
        assert "line_boxes" not in header_block

        # 表格页实测 0 个 ocr_text：整页不产出逐行框
        table_block = page_two["blocks"][1]
        assert "line_boxes" not in table_block

    def test_重叠的同行的框不会被当成两行(self) -> None:
        """回归：y 区间互相重叠的 ocr_text 是同一行的重复检测，不是两行。

        曾经有一条断言要求「content 1 行 + ocr_text 2 框」也挂上两个 line_boxes——
        那两个框的 y 区间是 [88,110] 与 [102,119]，**重叠了 8 个单位**。挂上去等于
        对外宣称这一行文字占了两个不同高度，坐标是假的。红线（框数 != 行数就放弃）
        必须对它生效，这里把这条语义单独锁住。
        """
        backend = _make_backend()
        with tempfile.TemporaryDirectory() as td:
            model = Path(td) / "x_model.json"
            model.write_text(_model_json_sample())
            lines = backend._parse_model_json_lines(model)

        first, second = lines[1][0]["bbox"], lines[1][1]["bbox"]
        overlap = min(first[3], second[3]) - max(first[1], second[1])
        assert overlap > 0, "夹具的前提是两个框 y 区间重叠（同一行的重复检测）"

        # 单行 content + 两个重叠框 → 必须放弃
        page_blocks = [{"type": "text", "text": "地址：某某路 电话：123", "bbox": [209, 89, 666, 118]}]
        attached, skipped = backend._attach_ocr_text_lines(page_blocks, lines[1])
        assert attached == 0
        assert skipped == 1
        assert "line_boxes" not in page_blocks[0]

    def test_框数与行数一致时才挂(self) -> None:
        """正面场景：2 行 content + 2 个不重叠的框 → 挂上，且按 y 升序。"""
        backend = _make_backend()
        page_blocks = [
            {
                "type": "text",
                "text": "第一行\n第二行",
                "bbox": [100, 100, 900, 300],
            }
        ]
        ocr_lines = [
            {"bbox": [100, 200, 400, 240], "type": "ocr_text"},  # 倒序存放
            {"bbox": [100, 110, 500, 150], "type": "ocr_text"},
        ]
        attached, skipped = backend._attach_ocr_text_lines(page_blocks, ocr_lines)
        assert (attached, skipped) == (1, 0)
        assert [b["bbox"][1] for b in page_blocks[0]["line_boxes"]] == [110, 200]

    def test_missing_model_json_keeps_block_level_bbox(self) -> None:
        """没有 model.json 时退回原行为：只有块级 bbox，不挂 line_boxes。"""
        backend = _make_backend()
        zip_bytes = _make_zip_bytes(
            {
                "result/test_content_list.json": _content_list_with_text_blocks(),
                "result/output.md": "地址：某某路 电话：123",
            }
        )

        with _patch_http(MagicMock(), content=zip_bytes):
            result = backend._parse_result_zip("https://example.com/result.zip")

        assert "地址：某某路" in result.text
        for page in result.layout["pages"]:
            for block in page["blocks"]:
                assert "line_boxes" not in block

    def test_broken_model_json_degrades_to_block_level_bbox(self) -> None:
        """model.json 损坏时只丢逐行坐标，不影响主链路。"""
        backend = _make_backend()
        zip_bytes = _make_zip_bytes(
            {
                "result/test_content_list.json": _content_list_with_text_blocks(),
                "result/test_model.json": "not json!!!",
                "result/output.md": "地址：某某路 电话：123",
            }
        )

        with _patch_http(MagicMock(), content=zip_bytes):
            result = backend._parse_result_zip("https://example.com/result.zip")

        assert "地址：某某路" in result.text
        assert "line_boxes" not in result.layout["pages"][0]["blocks"][0]

    def test_with_markdown_only(self) -> None:
        backend = _make_backend()
        zip_bytes = _make_zip_bytes(
            {
                "result/output.md": "# 标题\n\n这是正文内容",
            }
        )

        mock_client = MagicMock()

        with _patch_http(mock_client, content=zip_bytes):
            result = backend._parse_result_zip(
                "https://example.com/result.zip",
                return_markdown=True,
            )

        assert result.markdown == "# 标题\n\n这是正文内容"
        assert "正文内容" in result.text

    def test_with_images(self) -> None:
        backend = _make_backend()
        zip_bytes = _make_zip_bytes(
            {
                "result/output.md": "text",
                "result/img_0.jpg": b"\xff\xd8\xff\xe0",
                "result/img_1.png": b"\x89PNG",
            }
        )

        mock_client = MagicMock()

        with _patch_http(mock_client, content=zip_bytes):
            result = backend._parse_result_zip(
                "https://example.com/result.zip",
                extract_images=True,
            )

        assert result.images is not None
        assert len(result.images) == 2
        assert result.metadata["has_images"] is True
        assert result.metadata["image_count"] == 2

    def test_no_images_extract_images_false(self) -> None:
        backend = _make_backend()
        zip_bytes = _make_zip_bytes({"result/output.md": "text"})

        mock_client = MagicMock()

        with _patch_http(mock_client, content=zip_bytes):
            result = backend._parse_result_zip(
                "https://example.com/result.zip",
                extract_images=False,
            )

        assert result.images is None

    def test_bad_zip_raises(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock()

        with _patch_http(mock_client, content=b"not a zip"):
            with pytest.raises(MineruAPIError, match="ZIP 文件损坏"):
                backend._parse_result_zip("https://example.com/result.zip")

    def test_empty_zip_no_text(self) -> None:
        backend = _make_backend()
        zip_bytes = _make_zip_bytes({"result/readme.txt": "no useful content"})

        mock_client = MagicMock()

        with _patch_http(mock_client, content=zip_bytes):
            result = backend._parse_result_zip("https://example.com/result.zip")

        assert result.text == ""

    @staticmethod
    def _zip_with_fake_declared_size(declared_size: int) -> bytes:
        """构造 ZIP：central directory 声明的解压后大小为 declared_size（实际数据极小）。"""
        import io
        import struct

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("result/huge.bin", b"tiny")
        data = buf.getvalue()
        cd_offset = data.rfind(b"PK\x01\x02")
        assert cd_offset != -1
        return data[: cd_offset + 24] + struct.pack("<I", declared_size) + data[cd_offset + 28 :]

    def test_zip_bomb_declared_size_rejected(self) -> None:
        """解压炸弹防护：声明解压 3GB 的 ZIP 被拒绝，不执行 extractall。"""
        backend = _make_backend()
        bomb = self._zip_with_fake_declared_size(3 * 1024 * 1024 * 1024)
        mock_client = MagicMock()

        with _patch_http(mock_client, content=bomb):
            with pytest.raises(MineruAPIError, match="安全解压上限"):
                backend._parse_result_zip("https://example.com/result.zip")

    def test_zip_bomb_member_count_rejected(self) -> None:
        """解压炸弹防护：成员数超过上限的 ZIP 被拒绝。"""
        from apps.core.filesystem.filesystem_service import ZIP_MAX_MEMBER_COUNT

        backend = _make_backend()
        zip_bytes = _make_zip_bytes({f"result/m{i}.txt": "x" for i in range(ZIP_MAX_MEMBER_COUNT + 1)})
        mock_client = MagicMock()

        with _patch_http(mock_client, content=zip_bytes):
            with pytest.raises(MineruAPIError, match="安全解压上限"):
                backend._parse_result_zip("https://example.com/result.zip")


# ── _extract_text_from_content_list ──────────────────────────────


class TestExtractTextFromContentList:
    def test_normal(self, tmp_path: Path) -> None:
        cl = tmp_path / "content_list.json"
        cl.write_text(
            json.dumps(
                [
                    {"type": "text", "text": "段落一"},
                    {"type": "table", "text": "表格"},
                    {"type": "text", "text": "段落二"},
                ]
            )
        )

        backend = _make_backend()
        text = backend._extract_text_from_content_list(cl)
        assert text == "段落一\n段落二"

    def test_empty_list(self, tmp_path: Path) -> None:
        cl = tmp_path / "content_list.json"
        cl.write_text("[]")

        backend = _make_backend()
        text = backend._extract_text_from_content_list(cl)
        assert text == ""

    def test_no_text_blocks(self, tmp_path: Path) -> None:
        cl = tmp_path / "content_list.json"
        cl.write_text(
            json.dumps(
                [
                    {"type": "table", "text": "表格内容"},
                    {"type": "image", "text": ""},
                ]
            )
        )

        backend = _make_backend()
        text = backend._extract_text_from_content_list(cl)
        assert text == ""

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        cl = tmp_path / "content_list.json"
        cl.write_text("not json!!!")

        backend = _make_backend()
        text = backend._extract_text_from_content_list(cl)
        assert text == ""


# ── extract_text ─────────────────────────────────────────────────


class TestExtractText:
    def test_success(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_result = ParsedDocument(text="hello world", parse_method="mineru")

        with patch.object(backend, "parse_document", return_value=mock_result):
            result = backend.extract_text(str(pdf))

        assert isinstance(result, TextExtractionResult)
        assert result.success is True
        assert result.text == "hello world"
        assert result.method == "mineru"

    def test_max_length_truncates(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_result = ParsedDocument(text="a" * 1000, parse_method="mineru")

        with patch.object(backend, "parse_document", return_value=mock_result):
            result = backend.extract_text(str(pdf), max_length=10)

        assert len(result.text) == 10

    def test_failure_returns_error_result(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()

        with patch.object(backend, "parse_document", side_effect=Exception("boom")):
            result = backend.extract_text(str(pdf))

        assert result.success is False
        assert result.text == ""
        assert "boom" in result.metadata["error"]


# ── parse_document (端到端) ──────────────────────────────────────


class TestParseDocument:
    def test_file_not_found(self) -> None:
        backend = _make_backend()
        with pytest.raises(FileNotFoundError):
            backend.parse_document("/nonexistent/file.pdf")

    def test_full_flow(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        zip_bytes = _make_zip_bytes(
            {
                "result/test_content_list.json": json.dumps(
                    [
                        {"type": "text", "text": "解析成功"},
                    ]
                ),
                "result/output.md": "# 成功",
            }
        )

        mock_client = MagicMock()
        # batch API
        mock_client.post.return_value = _mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "batch_id": "batch-456",
                    "file_urls": ["https://oss.example.com/upload"],
                },
            },
        )
        # PUT upload
        mock_client.put.return_value = _mock_response(200)
        # GET: poll → done（结果 ZIP 走 client.stream 流式下载）
        poll_resp = _mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "state": "done",
                            "full_zip_url": "https://example.com/result.zip",
                        }
                    ],
                },
            },
        )
        mock_client.get.return_value = poll_resp

        with _patch_http(mock_client, content=zip_bytes), patch(f"{_PATCH_PREFIX}.time.sleep"):
            result = backend.parse_document(str(pdf), return_markdown=True)

        assert "解析成功" in result.text
        assert result.markdown == "# 成功"
        assert result.parse_method == "mineru"

    def test_mineru_error_reraised(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_response(
            200,
            {
                "code": -1,
                "msg": "api error",
            },
        )

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            with pytest.raises(MineruAPIError, match="api error"):
                backend.parse_document(str(pdf))

    def test_unexpected_error_wrapped(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        with patch.object(backend, "_upload_file", side_effect=RuntimeError("unexpected")):
            with pytest.raises(MineruAPIError, match="unexpected"):
                backend.parse_document(str(pdf))


# ── 大文件上传：超时口径 / 流式 / 重试 ───────────────────────────
#
# 回归背景：上传曾经用 `self.timeout`（默认 30s）且 `f.read()` 整包进内存。
# 65MB 卷宗实测 `write operation timed out`，双引擎里 MinerU 这一侧永远没有
# 结果，只剩 PaddleOCR-VL 单边——比对失去意义。


class TestUploadTimeoutBudget:
    """上传超时必须随体积增长，且各阶段口径不同。"""

    def test_小文件不低于下限(self) -> None:
        backend = _make_backend()
        timeout = backend._upload_timeout_for(1024)  # 1KB
        # 连接/写阶段有小文件底，不至于握个手就被判超时
        assert timeout.connect == backend.UPLOAD_MIN_TIMEOUT
        assert timeout.read >= backend.UPLOAD_MIN_TIMEOUT

    def test_大文件超时随体积增长(self) -> None:
        backend = _make_backend()
        small = backend._upload_timeout_for(1 * 1024 * 1024)  # 1MB
        big = backend._upload_timeout_for(65 * 1024 * 1024)  # 65MB
        assert big.read > small.read, "65MB 必须比 1MB 给更多时间，否则就是本次事故复现"
        # 30s 是元数据超时，绝不能拿来传 65MB
        assert big.read > 30 * 10

    def test_超时有上限不会无限挂(self) -> None:
        backend = _make_backend()
        huge = backend._upload_timeout_for(10 * 1024 * 1024 * 1024)  # 10GB
        assert huge.read <= backend.UPLOAD_MAX_TIMEOUT

    def test_显式指定时以指定值为准(self) -> None:
        backend = MineruBackend(api_key="k", upload_timeout=42)
        timeout = backend._upload_timeout_for(65 * 1024 * 1024)
        assert timeout.read == 42


class TestUploadStreaming:
    """文件本体必须流式上传，不能整包读进内存。"""

    def test_传入的是文件句柄而不是整包字节(self, tmp_path: Path) -> None:
        pdf = tmp_path / "big.pdf"
        pdf.write_bytes(b"%PDF-1.4" + b"x" * (2 * 1024 * 1024))

        backend = _make_backend()
        upload_ctx, upload_client = _mock_upload_client()

        with patch(f"{_PATCH_PREFIX}.httpx.Client", return_value=upload_ctx):
            backend._put_file_streaming("https://oss.example.com/u?sig=1", pdf)

        upload_client.put.assert_called_once()
        content = upload_client.put.call_args.kwargs["content"]
        # 关键：传给 httpx 的是可读文件对象，不是 bytes。
        # 整包 read() 会让 65MB 常驻内存；用句柄 httpx 分块读盘，
        # 还能据此算出 Content-Length（预签名校验需要）。
        assert hasattr(content, "read")
        assert not isinstance(content, (bytes, bytearray))

    def test_重试时重开文件避免传出残缺字节(self, tmp_path: Path) -> None:
        """一次失败的 PUT 可能已把句柄读空；复用偏移量会传一份残缺内容。"""
        import httpx

        pdf = tmp_path / "r.pdf"
        pdf.write_bytes(b"%PDF-1.4 payload")

        backend = _make_backend()
        calls: list[bool] = []

        def _put(_url, content=None, **_kw):
            # 每次都必须是尾部为 0（新开的句柄）
            calls.append(content.tell() == 0)
            if len(calls) < 2:
                raise httpx.ConnectError("boom")
            return _mock_response(200)

        upload_ctx, upload_client = _mock_upload_client()
        upload_client.put.side_effect = _put

        with (
            patch(f"{_PATCH_PREFIX}.httpx.Client", return_value=upload_ctx),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
        ):
            backend._put_file_streaming("https://oss.example.com/u?sig=1", pdf)

        assert calls == [True, True], "重试必须重新从文件头开始读"

    def test_重试耗尽后报错而不是静默成功(self, tmp_path: Path) -> None:
        import httpx

        pdf = tmp_path / "f.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        backend = _make_backend()
        upload_ctx, upload_client = _mock_upload_client()
        upload_client.put.side_effect = httpx.ConnectError("always down")

        with (
            patch(f"{_PATCH_PREFIX}.httpx.Client", return_value=upload_ctx),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
            pytest.raises(MineruAPIError, match="文件上传失败"),
        ):
            backend._put_file_streaming("https://oss.example.com/u?sig=1", pdf)

        assert upload_client.put.call_count == backend.UPLOAD_ATTEMPTS

    def test_文件不存在时给出明确错误(self, tmp_path: Path) -> None:
        backend = _make_backend()
        with pytest.raises(MineruAPIError, match="待上传文件不存在"):
            backend._upload_file(str(tmp_path / "nope.pdf"))


class TestPollTimeoutIsEnforced:
    """POLL_TIMEOUT 必须真的生效——这是一个曾经完全失效的配置。

    ## 事故（2026-11-16，164 页全本双引擎）

    配置写的是 `POLL_TIMEOUT = 360`，但 MinerU 那一路实际跑了 **4347 秒**（72 分钟）。
    期间日志里「轮询请求失败」只有 8 条 —— 绝大部分时间在**静默阻塞**。

    根因：httpx 的 `timeout` 是「单次连接/读写」超时，不是墙钟总时长。TCP 连接
    半死时内核按系统级重传策略死等（macOS 默认 75s 起，多次重传可达十几分钟），
    这期间 `client.get()` 不返回，`while` 里那句 `elapsed > POLL_TIMEOUT`
    永远轮不到执行。

    所以这里锁两件事：
    1. 单次请求用的是**短超时**（POLL_REQUEST_TIMEOUT），不是元数据的 30s；
    2. 累计时长真的超了就抛 ParsingTimeoutError，且文案里带实际耗时与最后状态。
    """

    def test_单次请求用短超时而不是元数据超时(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(
            200,
            {"code": 0, "data": {"extract_result": [{"state": "done", "full_zip_url": "https://e.com/r.zip"}]}},
        )
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_client
        ctx.__exit__.return_value = False

        with (
            patch(f"{_PATCH_PREFIX}.httpx.Client", return_value=ctx) as client_cls,
            patch(f"{_PATCH_PREFIX}.time.sleep"),
        ):
            backend._poll_batch_result("batch-x")

        timeout_used = client_cls.call_args.kwargs["timeout"]
        assert timeout_used == backend.POLL_REQUEST_TIMEOUT
        assert timeout_used < backend.timeout, "单次轮询必须比元数据超时更短，否则半死连接会拖住整个循环"

    def test_累计超时时抛出并带上实际耗时与最后状态(self) -> None:
        """云端一直在 running（请求都成功）→ 靠 POLL_TIMEOUT 收口。"""
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(
            200, {"code": 0, "data": {"extract_result": [{"state": "running"}]}}
        )
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_client
        ctx.__exit__.return_value = False

        # 让时间每次都跨过阈值：第一次进入循环就判超时
        clock = iter([0.0, 10_000.0] + [10_000.0] * 50)
        with (
            patch(f"{_PATCH_PREFIX}.httpx.Client", return_value=ctx),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
            patch(f"{_PATCH_PREFIX}.time.time", side_effect=lambda: next(clock)),
        ):
            with pytest.raises(ParsingTimeoutError) as exc:
                backend._poll_batch_result("batch-timeout")

        message = str(exc.value)
        assert "任务超时" in message
        assert "实际" in message, "必须带实际耗时，否则无法区分「云端真慢」与「本地网络死了」"

    def test_连续失败达到上限就放弃而不是空转到超时(self) -> None:
        """本地网络/代理挂了 → 请求一直失败，靠连续失败计数收口。

        与上一条是两条不同的路：这里请求根本没成功过，重试再多次也不会自愈，
        只会白占 worker 槽位。
        """
        import httpx

        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("network down")
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_client
        ctx.__exit__.return_value = False

        with (
            patch(f"{_PATCH_PREFIX}.httpx.Client", return_value=ctx),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
            pytest.raises(MineruAPIError, match="连续失败"),
        ):
            backend._poll_batch_result("batch-net-down")

        assert mock_client.get.call_count == backend.POLL_MAX_CONSECUTIVE_ERRORS

    def test_成功响应会重置连续失败计数(self) -> None:
        """连续失败只算「一直失败」：中途成功过一次就重新计数。

        否则一个偶发抖动的网络（每次失败之间夹着成功）会被误判成「网络不可用」，
        把其实还活着的任务提前判死。

        不用 mock 时钟（那容易造出无限循环）：让「成功响应」在第 N 次后直接给 done。
        只要计数被正确重置，就一定能走到那个 done；若「成功不重置计数」，
        连续失败会一路累加到上限而先抛错。
        """
        import httpx

        backend = _make_backend()
        counter = {"n": 0}
        done_resp = _mock_response(
            200,
            {"code": 0, "data": {"extract_result": [{"state": "done", "full_zip_url": "https://e.com/r.zip"}]}},
        )

        def _get(*_a, **_kw):
            counter["n"] += 1
            if counter["n"] > backend.POLL_MAX_CONSECUTIVE_ERRORS * 2:
                return done_resp
            if counter["n"] % 2 == 1:
                raise httpx.ConnectError("blip")
            return _mock_response(200, {"code": 0, "data": {"extract_result": [{"state": "waiting-file"}]}})

        mock_client = MagicMock()
        mock_client.get.side_effect = _get
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_client
        ctx.__exit__.return_value = False

        with (
            patch(f"{_PATCH_PREFIX}.httpx.Client", return_value=ctx),
            patch(f"{_PATCH_PREFIX}.time.sleep"),
        ):
            result = backend._poll_batch_result("batch-flaky")

        assert result["state"] == "done", "偶发断连不应被判成「网络不可用」"
        assert counter["n"] > backend.POLL_MAX_CONSECUTIVE_ERRORS


# ── 批量上传 payload（is_ocr 嵌套位置） ──────────────────────────


class TestBatchUploadPayload:
    """``/api/v4/file-urls/batch`` 的 payload 字段与嵌套层级。

    官方文档把批量接口的 OCR 开关写作 ``file.is_ocr``——即 **files 数组元素内的
    字段**；顶层的 ``is_ocr`` 只属于单文件接口 ``/api/v4/extract/task``。
    放错层服务端不报错，只是按默认 false 处理，扫描件解析出来是空白，所以这里
    逐字段钉死位置。
    """

    @staticmethod
    def _batch_ok_response() -> MagicMock:
        return _mock_response(
            200,
            {"code": 0, "data": {"batch_id": "batch-ocr", "file_urls": ["https://oss.example.com/upload?sig=abc"]}},
        )

    def _capture_payload(self, file_name: str) -> dict:
        """跑一次 `_request_upload_url`，返回真正发出去的 JSON body。"""
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.post.return_value = self._batch_ok_response()

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            batch_id, upload_url = backend._request_upload_url(file_name)

        assert batch_id == "batch-ocr"
        assert upload_url == "https://oss.example.com/upload?sig=abc"
        mock_client.post.assert_called_once()
        return mock_client.post.call_args.kwargs["json"]

    def test_pdf_元素内显式开启ocr(self) -> None:
        payload = self._capture_payload("劳动合同.pdf")

        assert payload["files"][0]["is_ocr"] is True
        # 顶层不能重复放：那是单文件接口的字段，混进批量接口只会误导后来人
        assert "is_ocr" not in payload

    def test_图片同样开启ocr(self) -> None:
        for name in ("扫描件.jpg", "照片.JPEG", "截屏.png"):
            payload = self._capture_payload(name)
            assert payload["files"][0]["is_ocr"] is True, name

    def test_办公文档不传ocr开关(self) -> None:
        """docx/xlsx/pptx 由 MinerU 自己排版转换，不传 `is_ocr` 走服务端默认。"""
        for name in ("起诉状.docx", "清单.xlsx", "证据.ppt", "明细.xls", "旧版.doc"):
            payload = self._capture_payload(name)
            assert "is_ocr" not in payload["files"][0], name

    def test_顶层公共参数(self) -> None:
        payload = self._capture_payload("卷宗.pdf")

        assert payload["model_version"] == MineruBackend.MODEL_VERSION
        assert payload["language"] == "ch"
        assert payload["enable_table"] is True
        # 取值与理由见 mineru_backend._ENABLE_FORMULA；这里只钉住「相当值的单一来源」，
        # 以后要改默认值只改那个常量，不必回来改断言。
        assert payload["enable_formula"] is mineru_backend._ENABLE_FORMULA

    def test_公式开关顶层与元素内取值一致(self) -> None:
        """``enable_formula`` 在顶层和 ``files[]`` 里各有一份，不能一处开一处关。

        批量接口的官方文档只把 ``enable_formula`` 列在顶层，元素内那一份是对齐
        ``file.is_ocr`` 的写法。两处不一致时，服务端按哪份生效没有文档保证——
        这种不确定性没必要时时去兜，钉死相等最省事。
        办公文档走服务端默认，不带这个字段，因此只对 ``_OCR_REQUIRED_SUFFIXES`` 断言。
        """
        for name in ("卷宗.pdf", "扫描件.jpg", "照片.PNG"):
            payload = self._capture_payload(name)
            assert payload["files"][0]["enable_formula"] is payload["enable_formula"], name

        office_payload = self._capture_payload("起诉状.docx")
        assert "enable_formula" not in office_payload["files"][0]

    def test_元素基础字段与公式开关(self) -> None:
        payload = self._capture_payload("卷宗.pdf")

        entry = payload["files"][0]
        assert entry["name"] == "卷宗.pdf"
        assert entry["data_id"], "data_id 用于回查业务数据，不能为空"
        assert len(payload["files"]) == 1
