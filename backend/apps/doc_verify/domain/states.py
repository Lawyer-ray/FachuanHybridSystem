"""核对状态的推导：报告说什么，状态才能说什么。

## 六个状态是六份不同的法律事实（不是六种颜色）

| 状态 | 事实 | 怎么推出来 |
|:--|:--|:--|
| identical | 字节相同（数字件原样回传） | `coverage["bytes_identical"] is True` |
| verified_clean | 正文真的比过了，断言全成立 | 无任何 findings，且 `coverage["text_compared"] is True`、`pages_no_text == 0` |
| no_difference_detected | 没花那份钱核正文，**未发现**差异——不等于「没改」 | 无任何 findings，正文没比或没比全 |
| changed | 红线命中或实质差异 | 有 red 或 yellow |
| unverifiable | 尝试过了仍取不到文本，不给绿灯 | 只有 gray |
| not_requested | 策略未要求，也没人手动点 | **推导不出来**：没有任何核对运行时才有它，由编排层直接给出 |

## 为什么 `verified_clean` 看 coverage 而不是 tier

tier 只说明「花了多少钱」，不说明「比了什么」：tier 0 也能逐字比数字件的文本层，比完
干净就是真的干净；反过来，tier 1 也可能有一半页没取到文本。拿 tier 当绿灯会把前一种
核对打成 `no_difference_detected`（对律师说了句「没核」的假话），把后一种打成
`verified_clean`（对律师说了句「核过了」的假话）。判据因此是覆盖度本身。

## 阻塞集合为什么不含 no_difference_detected

`BLOCKING_STATES` 是「检出问题、必须律师裁决才能放行」。`no_difference_detected` 是
「没花钱核」——把它并进阻塞集合，tier 0 的扫描回传件会永久红，结果一定是律师把功能
关掉。要不要升级到 tier 1 是**策略**（按 doc_type 判，见 `services/policy.py`），
不归状态机管。
"""

from __future__ import annotations

from apps.doc_verify.domain.contracts import Report

STATE_IDENTICAL = "identical"
STATE_VERIFIED_CLEAN = "verified_clean"
STATE_NO_DIFFERENCE_DETECTED = "no_difference_detected"
STATE_CHANGED = "changed"
STATE_UNVERIFIABLE = "unverifiable"
STATE_NOT_REQUESTED = "not_requested"

#: 需律师裁决才能放行的状态：检出问题（red/yellow）与「尝试过仍无法核对」（gray）。
BLOCKING_STATES: frozenset[str] = frozenset({STATE_CHANGED, STATE_UNVERIFIABLE})

#: 可以自动放行的状态：字节相同，或正文逐项比过且没有一条不成立。
PASS_STATES: frozenset[str] = frozenset({STATE_IDENTICAL, STATE_VERIFIED_CLEAN})


def derive_state(report: Report) -> str:
    """由发现项与覆盖度推导状态。顺序是硬的：字节相同 > 检出问题 > 无法核对 > 干净。"""
    if report.coverage.get("bytes_identical") is True:
        return STATE_IDENTICAL
    severities = {str(finding.severity) for finding in report.findings}
    if "red" in severities or "yellow" in severities:
        return STATE_CHANGED
    if "gray" in severities:
        return STATE_UNVERIFIABLE
    if _text_fully_compared(report):
        return STATE_VERIFIED_CLEAN
    return STATE_NO_DIFFERENCE_DETECTED


def _text_fully_compared(report: Report) -> bool:
    """正文是否真的逐页比过：比过（`text_compared`）且没有一页缺文本（`pages_no_text == 0`）。

    缺键一律按「没比过」处理：覆盖度是别人写的，读不到就等于没有证据。
    """
    return report.coverage.get("text_compared") is True and report.coverage.get("pages_no_text", 1) == 0
