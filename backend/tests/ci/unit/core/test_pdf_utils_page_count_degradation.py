"""`get_pdf_page_count_with_error` 的三级降级必须真的降级。

## 这些用例为什么存在

函数 docstring 承诺「降级策略: pikepdf → fitz → pdfplumber」，失败时返回
``(default, error_message)``。但实现里后两层曾经写的是:

    except (TypeError, ValueError) as e:

而两个解析库抛的都不是这两类:

    pymupdf  : FileDataError     —— MRO 是 [FileDataError, RuntimeError, Exception]
    pdfplumber: PdfminerException —— MRO 是 [PdfminerException, Exception]

于是「一份损坏 PDF」会在 fitz 那层直接**逃出函数**，既走不到 pdfplumber，
也拿不到承诺的 ``(default, error)``。调用方（证据上传、PDF 合并）没兜住就是 500。

上一版测试全是 mock（patch 掉 `pikepdf.open` 之类），从来没用**真实坏字节**跑过，
所以这个洞一直没被发现。这里补的就是那一层：不 mock 解析库，直接喂坏数据。
"""

from __future__ import annotations

import pytest

from apps.core.services.pdf_utils import get_pdf_page_count, get_pdf_page_count_with_error

# 三种真实的「看起来像 PDF / 完全不是 PDF / 结构残缺」形态。
# 它们分别对应：用户改了后缀名、用户传错文件、文件在传输中被截断。
CORRUPT_PAYLOADS = [
    pytest.param(b"%PDF-1.4 not really a pdf", id="garbage-pdf-header"),
    pytest.param(b"hello world", id="plain-text"),
    pytest.param(b"%PDF-1.7\n%%EOF\n", id="truncated-pdf"),
]


@pytest.mark.parametrize("payload", CORRUPT_PAYLOADS)
def test_corrupt_pdf_returns_default_instead_of_raising(payload: bytes) -> None:
    """坏 PDF 必须降级成 ``(default, 错误文案)``，绝不能把异常抛给调用方。

    这是本文件最重要的一条：它锁住的是「函数不食言」——
    承诺了降级就必须降级，而不是让底层库的异常类型决定成败。
    """
    count, error = get_pdf_page_count_with_error(payload, default=7)

    assert count == 7, "读不出页数时要用调用方给的 default，不能编一个数"
    assert error, "必须带回错误文案，调用方要据此提示用户「文件损坏」"


@pytest.mark.parametrize("payload", CORRUPT_PAYLOADS)
def test_corrupt_pdf_convenience_wrapper_returns_default(payload: bytes) -> None:
    """只取页数的便捷版同样不能抛——它内部就是上面那个函数。"""
    assert get_pdf_page_count(payload, default=3) == 3


def test_none_source_raises_value_error() -> None:
    """None 是**调用方的编程错误**，不是「坏文件」，因此要主动报错而不是静默降级。

    两者要分开看：
      · 坏 PDF  → 降级，返回 (default, error)，用户可以重传
      · None    → 抛 ValueError，这是代码 bug，静默返回 default 会把 bug 藏起来
    这里把这条边界固定下来，防止将来有人把降级写得过宽。
    """
    with pytest.raises(ValueError, match="source is None"):
        get_pdf_page_count_with_error(None, default=5)


def test_valid_pdf_still_reports_real_page_count() -> None:
    """回归护栏：修降级不能把正常路径也改成永远返回 default。

    构造一份最小的真 PDF（1 页空白），确认 pikepdf / fitz 能读出来。
    """
    pymupdf = pytest.importorskip("pymupdf")

    doc = pymupdf.open()
    doc.new_page()
    payload = doc.tobytes()
    doc.close()

    count, error = get_pdf_page_count_with_error(payload, default=99)
    assert error is None, f"正常 PDF 不该报错: {error}"
    assert count == 1
