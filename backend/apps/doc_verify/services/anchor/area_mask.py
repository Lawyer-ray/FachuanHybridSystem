"""允许变化的区域掩膜：哪些位置「本来就会变」，不该判为改动。

## 默认只掩「文末签署区」

客户回传时签名 / 日期 / 盖章必然与出站件不同。不掩掉这三行，每一份确认书都会
报一条假红；掩得更多（比如整页、或正文中段）就会把真改动（金额、当事人、
诉请项数）一起放过——那是拿「误报少」换「漏报」，对律师是更坏的方向。

所以默认只给高风险四类（起诉状 / 授权委托书 / 送达地址确认书 / 退费账户确认书）
一个形状固定的小掩膜：``{"kind": "signature_zone", "doc_type": <文书名>, "tail_lines": 3}``。
其它文书返回空列表：没有签署区的件不该有掩膜，宁可让比对去报差异。

## 为什么按 doc_type 精确匹配、不做模糊匹配

``doc_type`` 是调用方给的确切卷宗名（``OutboundArtifact.doc_type`` 定义即「卷宗写法」）。
关键字猜错一次，掩膜就套到别的文书上，而掩膜的错误方向永远是「少报改动」。
"""

from __future__ import annotations

from typing import Any

#: 掩膜形状里的固定类型标签
MASK_KIND_SIGNATURE_ZONE = "signature_zone"

#: 文末签署区默认覆盖的行数：签名、日期、盖章通常各占一行
SIGNATURE_ZONE_TAIL_LINES = 3

#: 默认给签署区掩膜的四个高风险文书（卷宗写法，与调用方传入的 doc_type 逐字比较）
SIGNATURE_ZONE_DOC_TYPES = frozenset(
    {
        "起诉状",
        "授权委托书",
        "送达地址确认书",
        "退费账户确认书",
    }
)


def default_masks(doc_type: str) -> list[dict[str, Any]]:
    """高风险四类默认给「文末签署区」掩膜；其它 doc_type 返回空列表。"""
    normalized = str(doc_type or "").strip()
    if normalized not in SIGNATURE_ZONE_DOC_TYPES:
        return []
    return [
        {
            "kind": MASK_KIND_SIGNATURE_ZONE,
            "doc_type": normalized,
            "tail_lines": SIGNATURE_ZONE_TAIL_LINES,
        }
    ]
