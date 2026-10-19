"""律所ID 同步：OA 案件详情（OACaseData）→ 新建合同表单回填数据整形。

纯函数、无 ORM。admin 视图拿到 ScriptExecutorService 返回的 OACaseData 后，
经本模块整形成表单可直接消费的 JSON（合同类型 / 收费模式 / 代理阶段枚举值、
ISO 日期、金额、详情 URL、当事人与律师名单）。当事人与律师只给名单，由前端
经 admin autocomplete 做精确匹配——新建页合同尚未保存，这里不落任何 Client / Lawyer 数据。
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.contracts.models import FeeMode
from apps.core.models.enums import CaseStage
from apps.oa_filing.services.case_import_service import map_oa_case_type_from_text, parse_date
from apps.oa_filing.services.oa_data_models import OACaseData, OACaseInfoData

# 与 JTNAdapter.build_case_detail_url 同款（contracts 不可 import jtn 子包，此处独立维护）
_DETAIL_URL_TEMPLATE = (
    "https://ims.jtn.com/project/projectView.aspx?keyid={keyid}&FirstModel=PROJECT&SecondModel=PROJECT002"
)

# OA「收费方式」原文 → FeeMode；顺序即优先级（「半风险」先于泛「风险」）。
# 真实值样本（2026-10-19）：「定额收费」；其余按关键词兜底，有值但无命中归 CUSTOM 并把原文放进自定义条款
_FEE_MODE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("半风险",), FeeMode.SEMI_RISK),
    (("全风险", "风险代理", "风险收费", "风险"), FeeMode.FULL_RISK),
    (("定额", "固定", "包干", "一次性"), FeeMode.FIXED),
)


def build_sync_payload(oa_data: OACaseData) -> dict[str, Any]:
    """OACaseData → 新建合同表单回填 JSON。

    合同类型沿用案件导入口径：案件类别优先、业务种类兜底；收案日期归一为
    ISO（解析不了给 None，前端跳过不填）。名单按名称去重保序。OA 没有的字段
    一律 None / 空，前端据此跳过，不硬填。
    """
    info = oa_data.case_info
    keyid = str(oa_data.keyid or "").strip().lower()
    acceptance = parse_date(str(_text(info, "acceptance_date"))) if info else None
    case_number = _text(info, "case_no") or str(oa_data.case_no or "").strip()
    fee_mode = _resolve_fee_mode(_text(info, "fee_mode_text"))

    return {
        "guid": keyid,
        "detail_url": _DETAIL_URL_TEMPLATE.format(keyid=keyid) if keyid else "",
        "case_number": case_number,
        "name": _text(info, "case_name"),
        "case_type": _resolve_case_type(info),
        "start_date": acceptance.isoformat() if acceptance else None,
        "case_stage": _text(info, "case_stage"),
        "representation_stages": _resolve_stages(_text(info, "case_stage")),
        "client_side": _text(info, "client_side"),
        "responsible_lawyer": _text(info, "responsible_lawyer"),
        "fee_mode": fee_mode,
        "fixed_amount": _normalize_amount(_text(info, "fee_amount_text")),
        "fee_currency": _text(info, "fee_currency"),
        "custom_terms": _build_custom_terms(info, fee_mode),
        "clients": [
            {"name": name, "customer_type": customer_type}
            for name, customer_type in _dedupe_named(
                (str(c.name or "").strip(), str(c.customer_type or "")) for c in oa_data.customers
            )
        ],
        "opponents": [
            {"name": name, "conflict_type": conflict_type}
            for name, conflict_type in _dedupe_named(
                (str(c.name or "").strip(), str(c.conflict_type or "")) for c in oa_data.conflicts
            )
        ],
    }


def _text(info: OACaseInfoData | None, field: str) -> str:
    """安全取 case_info 字段文本（None → ""）。"""
    if info is None:
        return ""
    return str(getattr(info, field, None) or "").strip()


def _resolve_case_type(info: OACaseInfoData | None) -> str | None:
    """案件类别优先、业务种类兜底（与 case_import_service._map_oa_case_type 同口径）。

    map_oa_case_type_from_text 返回 CaseType 枚举成员，这里收敛为纯字符串，
    JSON 里稳定输出 "civil" 这类 value 而非枚举 repr。
    """
    if info is None:
        return None
    mapped = map_oa_case_type_from_text(info.case_category) or map_oa_case_type_from_text(info.case_type)
    return str(mapped) if mapped else None


def _resolve_fee_mode(text: str) -> str | None:
    """OA 收费方式原文 → FeeMode value；空给 None（不动表单默认值），有值无命中归 CUSTOM。"""
    compact = "".join(text.split())
    if not compact:
        return None
    for keywords, mode in _FEE_MODE_RULES:
        if any(keyword in compact for keyword in keywords):
            return str(mode)
    return str(FeeMode.CUSTOM)


def _normalize_amount(text: str) -> str | None:
    """OA 合同总额原文 → 两位小数字符串；非数字 / 零（OA 未填默认 0.00）给 None 不填。"""
    raw = re.sub(r"[^\d.]", "", text.replace("，", ","))
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if value <= 0:
        return None
    return f"{value:.2f}"


def _build_custom_terms(info: OACaseInfoData | None, fee_mode: str | None) -> str:
    """自定义收费条款：仅当 OA 收费方式无法归入标准模式（CUSTOM）或标记了免费/减免时写入原文。"""
    fragments: list[str] = []
    if fee_mode == str(FeeMode.CUSTOM):
        fragments.append(f"OA 收费方式：{_text(info, 'fee_mode_text')}")
    if _text(info, "fee_waived") == "是":
        fragments.append("OA 标记：免费或减免代理")
    return "；".join(fragments)


def _resolve_stages(stage_text: str) -> list[str]:
    """OA 案件阶段原文 → CaseStage value 列表（精确 label 优先，再按最长 label 包含匹配）。

    长 label 优先避免「重审一审」被「一审」抢先；OA 阶段与本地枚举对不上则给空列表不填。
    """
    compact = "".join(stage_text.split())
    if not compact:
        return []
    choices = [(str(value), str(label)) for value, label in CaseStage.choices]
    for value, label in choices:
        if label == compact:
            return [value]
    for value, label in sorted(choices, key=lambda item: -len(item[1])):
        if label in compact:
            return [value]
    return []


def _dedupe_named(pairs: Any) -> list[tuple[str, str]]:
    """按名称去重保序；空名丢弃。"""
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for name, extra in pairs:
        if not name or name in seen:
            continue
        seen.add(name)
        result.append((name, extra))
    return result
