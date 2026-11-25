"""核对层级（tier）的升级规则：谁有权把一次核对从免费层抬到 OCR 层。

## 只有两种升级理由

- **调用方显式要求**（`requested >= 1`）：手动重核、基线自检。原样返回，不降级——
  降级等于替调用方改了主张。
- **律师在归案时勾了「回传后核对内容」**（`verify_required`）**且入站件没有文本层**：
  扫描件在免费层一个字都比不了，勾了核对就是对「为它花钱」的授权。

没勾就不自作主张：OCR 有成本，批量案件里替律师做这个决定，账单会替律师记住它。

## 为什么判据是「入站件有没有文本层」而不是「文书名像不像扫描件」

提取结果（`Inbound.text`）是唯一事实来源。按文书名、扩展名或指纹去猜「这份大概
是扫描的」，猜错的两个方向都糟：猜成扫描件会白花钱，猜成数字件会让扫描件静默
落到 `no_difference_detected`，而律师会把它读成「没改」。
"""

from __future__ import annotations

#: 免费层：页数 / 页指纹 / 数字件已有的文本层。
TIER_FREE = 0

#: OCR 层：对没有文本层的入站件花钱补字。
TIER_OCR = 1


def resolve_tier(*, requested: int | None, verify_required: bool, inbound_text: str) -> int:
    """算出**实际**要跑的层级（落库的 `VerificationRun.tier` 用这个值，不用入参）。

    三档语义分得很硬，因为它们对应三种不同的钱：

    - `requested >= 1`：调用方显式要求花钱，原样返回，不降级；
    - `requested == 0`：调用方显式要**免费层**（「先看一眼，别花钱」）——必须尊重。
      把 0 也自动升级，就等于替律师改了他刚刚做出的决定，还会让「免费层不撒谎」
      这条断言（扫描件只能是灰的 `no_difference_detected`）永远无法成立；
    - `requested is None`（未指定）：才走自动判定——律师勾了「回传后核对内容」
      且入站件整篇没有文本层，说明这是扫描件且他授权为它花钱，升到 OCR 层。

    没勾就不自作主张：OCR 有成本，批量案件里替律师做这个决定，账单会替律师记住它。
    """
    if requested is not None:
        return requested
    if verify_required and not str(inbound_text or "").strip():
        return TIER_OCR
    return TIER_FREE
