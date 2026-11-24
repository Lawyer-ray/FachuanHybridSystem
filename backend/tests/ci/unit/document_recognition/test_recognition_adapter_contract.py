"""识别服务适配器的契约测试（防「管线传了参数、适配器不认」这类 500 级事故）。

## 为什么要有这条用例

2026-11-24 的改动给 ``recognize_document`` 加了 ``sibling_documents`` 参数，并把
worker（``tasks.py``）改成按关键字传入。但 ``ServiceLocator`` 返回的是
``CourtDocumentRecognitionServiceAdapter``，它的签名没跟着加——于是**每一个**识别
任务都会抛 ``TypeError: recognize_document() got an unexpected keyword argument``，
被兜底记成 FAILED，候选一条都不会产出。

单元测试没红是因为 ``tasks.py`` 的用例用 ``MagicMock`` 顶替 service（MagicMock 接受
任意 kwargs）。这里用两条静态契约把这一类漏传锁死：

1. 协议（``ICourtDocumentRecognitionService``）声明的参数，适配器必须全部具备；
2. 适配器必须把它声明的每一个关键字参数**原样透传**给内部服务。
"""

from __future__ import annotations

import inspect
from typing import Any

from apps.core.protocols.court_protocols import ICourtDocumentRecognitionService
from apps.document_recognition.services import adapter as adapter_module
from apps.document_recognition.services.adapter import CourtDocumentRecognitionServiceAdapter
from apps.document_recognition.services.data_classes import DocumentType, RecognitionResponse, RecognitionResult

#: 适配器声明的全部关键字参数（新增参数必须同时出现在这里 → 强制有人确认透传）
EXPECTED_KEYWORD_ARGS = {
    "prebound_case_id",
    "prebound_case_log_id",
    "llm_model",
    "known_case_number",
    "known_party_names",
    "known_document_type",
    "received_at",
    "sibling_documents",
}


def test_adapter_declares_expected_keyword_args() -> None:
    params = inspect.signature(CourtDocumentRecognitionServiceAdapter.recognize_document).parameters
    actual = {name for name, p in params.items() if p.kind is inspect.Parameter.KEYWORD_ONLY}
    assert actual == EXPECTED_KEYWORD_ARGS, (
        "适配器关键字参数变了：新增参数必须同时确认「透传」并更新本清单，"
        f"否则 worker 按关键字调用会 TypeError。差异={actual ^ EXPECTED_KEYWORD_ARGS}"
    )


def test_protocol_parameters_are_all_supported_by_adapter() -> None:
    """协议里声明的参数，适配器一个都不能少。"""
    protocol_params = set(inspect.signature(ICourtDocumentRecognitionService.recognize_document).parameters)
    adapter_params = set(inspect.signature(CourtDocumentRecognitionServiceAdapter.recognize_document).parameters)
    missing = protocol_params - adapter_params
    assert missing == set(), f"适配器缺少协议参数: {sorted(missing)}（管线按关键字调用会 TypeError）"


def test_adapter_forwards_every_keyword_argument(monkeypatch: Any) -> None:
    """适配器声明的每个关键字参数都必须原样传给内部服务。"""
    captured: dict[str, Any] = {}

    class _Inner:
        def recognize_document(self, file_path: str, user: Any = None, **kwargs: Any) -> RecognitionResponse:
            captured["file_path"] = file_path
            captured.update(kwargs)
            return RecognitionResponse(
                recognition=RecognitionResult(
                    document_type=DocumentType.OTHER,
                    case_number=None,
                    key_time=None,
                    raw_text="",
                    confidence=0.0,
                    extraction_method="test",
                ),
                binding=None,
                file_path=file_path,
            )

    monkeypatch.setattr(adapter_module, "_build_service", lambda: _Inner())

    kwargs: dict[str, Any] = {
        "prebound_case_id": 1,
        "prebound_case_log_id": 2,
        "llm_model": "kimi-2.6",
        "known_case_number": "（20XX）粤0000民初0000号",
        "known_party_names": ["甲公司"],
        "known_document_type": "other",
        "received_at": None,
        "sibling_documents": ["某交费通知书.pdf"],
    }
    CourtDocumentRecognitionServiceAdapter().recognize_document("/tmp/doc.pdf", None, **kwargs)

    for name, value in kwargs.items():
        assert name in captured, f"适配器吞掉了参数 {name}（内部服务收不到）"
        assert captured[name] == value
