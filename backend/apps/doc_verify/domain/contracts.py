"""三层之间唯一的契约：数据形状在这里，实现分散在各自模块。

**为什么先立契约**：比对引擎（纯函数）、基线捕获（IO）、核对编排（DB）
三条线并行开发时，彼此只能依赖本文件。任何一方要改形状，必须先改这里，
否则第三条线的报告会静默错位（多一个字段没人读，少一个字段 KeyError）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class Severity(StrEnum):
    """三档，对应三种处置，不是三种颜色。"""

    RED = "red"  # 红线：字段级不一致，未裁决前不得进入送法院/用印
    YELLOW = "yellow"  # 疑似：全文实质差异，律师确认后可放行
    GRAY = "gray"  # 无法核对：图片页/无文本层，不给绿灯


class AssertionKind(StrEnum):
    """五级断言：粗粒度先拦，细粒度再列。"""

    PACKAGE = "package"  # 份数 / 文书名集合 / 页数
    PAGE = "page"  # 页序 / 缺页 / 多页 / 整页替换
    FIELD = "field"  # 金额 / 日期 / 当事人 / 案号 / 诉请项数
    PARAGRAPH = "paragraph"  # 段落存在性 + 首末句锚点 + 段序
    COVERAGE = "coverage"  # 覆盖率断言：哪几页/哪几项根本没法比


@dataclass(frozen=True)
class Finding:
    """一条失败项。

    code 是稳定机器码（前端折叠与统计按它聚合，不按 title 聚合——title 会改），
    title 给人看。
    """

    kind: AssertionKind
    code: str
    title: str
    severity: Severity = Severity.YELLOW
    detail: str = ""
    expected: str = ""
    actual: str = ""
    page: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "code": self.code,
            "title": self.title,
            "severity": str(self.severity),
            "detail": self.detail,
            "expected": self.expected,
            "actual": self.actual,
            "page": self.page,
        }


@dataclass(frozen=True)
class Baseline:
    """出站件基线（内存形状）。"""

    doc_type: str
    version: str
    sha256: str
    page_count: int
    page_signatures: tuple[tuple[float, ...], ...] = ()
    text: str = ""
    masks: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Inbound:
    """入站回传件。与 Baseline 同一个形状，两侧才能跑同一套断言。"""

    sha256: str
    page_count: int
    page_signatures: tuple[tuple[float, ...], ...] = ()
    text: str = ""
    file_name: str = ""


@dataclass
class Report:
    """一次核对的产出：失败清单 + 覆盖度。

    state 由发现项**推导**（见 domain/states.py），不允许调用方自己拍：
    只要存在一条 gray，就不能给 verified_clean——否则报告会说一句没有证据的话。
    """

    findings: list[Finding] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    tier: int = 0

    def findings_dicts(self) -> list[dict[str, Any]]:
        return [f.as_dict() for f in self.findings]


Tier = Literal[0, 1, 2]
