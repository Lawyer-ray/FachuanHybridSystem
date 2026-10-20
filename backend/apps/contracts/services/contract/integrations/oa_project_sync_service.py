"""律所ID 同步：OA 案件详情（OACaseData）→ 新建合同表单回填数据整形。

纯函数、无 ORM。admin 视图拿到 ScriptExecutorService 返回的 OACaseData 后，
经本模块整形成表单可直接消费的 JSON（合同类型 / 收费模式 / 代理阶段枚举值、
ISO 日期、金额、详情 URL、当事人与律师名单）。当事人与律师只给名单，本地
Client 的匹配/自动创建由 oa_party_resolution_service 负责（本模块不落任何数据）。
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.contracts.models import FeeMode
from apps.core.models.enums import CaseStage, CaseType
from apps.oa_filing.services.case_import_service import map_oa_case_type_from_text, parse_date
from apps.oa_filing.services.oa_data_models import OACaseCustomerData, OACaseData, OACaseInfoData, OAConflictData

# 与 JTNAdapter.build_case_detail_url 同款（contracts 不可 import jtn 子包，此处独立维护）
_DETAIL_URL_TEMPLATE = (
    "https://ims.jtn.com/project/projectView.aspx?keyid={keyid}&FirstModel=PROJECT&SecondModel=PROJECT002"
)

# OA「收费方式」原文 → FeeMode；顺序即优先级（「半风险」先于泛「风险」）。
# 真实值样本（2026-10-19）：「定额收费」→ 固定；「标的比例收费」无命中 → CUSTOM 并把原文放进自定义条款
# （按标的额比例计费与本地四种模式不一一对应，保留原文比强归某一类更有信息量）
_FEE_MODE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("半风险",), FeeMode.SEMI_RISK),
    (("全风险", "风险代理", "风险收费", "风险"), FeeMode.FULL_RISK),
    (("定额", "固定", "包干", "一次性"), FeeMode.FIXED),
)

# 利冲条目法律地位含这些词 → 第三人类（不是对方，也不是我方）
_THIRD_PARTY_MARKERS = ("第三人", "利害关系", "第三方")


def build_sync_payload(oa_data: OACaseData) -> dict[str, Any]:
    """OACaseData → 新建合同表单回填 JSON。

    合同类型沿用案件导入口径：案件类别优先、业务种类兜底、劳动仲裁特判；收案日期归一为
    ISO（解析不了给 None，前端跳过不填）。当事人按「是否委托人」分阵营：OA「客户信息」
    tab 里的委托人才是我方当事人；利冲表里的其余相关方按法律地位分成对立方、同案其他
    当事人（与代理何方同法律地位，如共同被告）与第三人。只有对立方回填为对方当事人，
    其余两组只提示不填。名单按名称去重保序。OA 没有的字段一律 None / 空，前端据此跳过。
    """
    info = oa_data.case_info
    keyid = str(oa_data.keyid or "").strip().lower()
    acceptance = parse_date(str(_text(info, "acceptance_date"))) if info else None
    case_number = _text(info, "case_no") or str(oa_data.case_no or "").strip()
    fee_mode = _resolve_fee_mode(_text(info, "fee_mode_text"))
    side = _text(info, "client_side")
    clients = _dedupe_customers(oa_data.customers)
    client_names = {str(c["name"]) for c in clients}
    groups = _split_conflicts(oa_data.conflicts, side=side, exclude_names=client_names)
    # 利冲表「类别：委托方」的条目也是我方当事人（客户 tab 漏列时兜底），并入委托人名单
    clients.extend(groups.pop("client"))

    return {
        "guid": keyid,
        "detail_url": _DETAIL_URL_TEMPLATE.format(keyid=keyid) if keyid else "",
        "case_number": case_number,
        "name": _text(info, "case_name"),
        "case_type": _resolve_case_type(info),
        "start_date": acceptance.isoformat() if acceptance else None,
        "case_stage": _text(info, "case_stage"),
        "representation_stages": _resolve_stages(_text(info, "case_stage")),
        "client_side": side,
        "responsible_lawyer": _text(info, "responsible_lawyer"),
        "fee_mode": fee_mode,
        "fixed_amount": _normalize_amount(_text(info, "fee_amount_text")),
        "fee_currency": _text(info, "fee_currency"),
        "custom_terms": _build_custom_terms(info, fee_mode),
        "clients": clients,
        "opponents": groups["opponent"],
        "co_parties": groups["co_party"],
        "third_parties": groups["third"],
    }


def _text(info: OACaseInfoData | None, field: str) -> str:
    """安全取 case_info 字段文本（None → ""）。"""
    if info is None:
        return ""
    return str(getattr(info, field, None) or "").strip()


def _resolve_case_type(info: OACaseInfoData | None) -> str | None:
    """案件类别优先、业务种类兜底、劳动仲裁特判（与 case_import_service._map_oa_case_type 同口径）。

    OA「案件类别」里的「仲裁案件」同时覆盖商事仲裁和劳动仲裁，先命中商事仲裁；业务种类明确为
    劳动人事争议仲裁时落劳动仲裁。map_oa_case_type_from_text 返回 CaseType 枚举成员，
    这里收敛为纯字符串，JSON 里稳定输出 "civil" 这类 value 而非枚举 repr。
    """
    if info is None:
        return None
    category_mapped = map_oa_case_type_from_text(info.case_category)
    business_mapped = map_oa_case_type_from_text(info.case_type)
    if category_mapped == CaseType.INTL and business_mapped == CaseType.LABOR:
        return str(CaseType.LABOR)
    mapped = category_mapped or business_mapped
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


def _split_conflicts(
    conflicts: list[OAConflictData], *, side: str, exclude_names: set[str]
) -> dict[str, list[dict[str, str]]]:
    """利冲条目按 OA「类别」分四组（各组按名去重保序；空字段不输出）。

    OA 分组标题自带阵营标注（类别：委托方 / 委托方关联方 / 对方当事人），比「法律地位」
    权威：我方被告案里类别为「对方当事人」的共同被告也是对方（律所没代理他们），要回填；
    「委托方关联方」是与委托人有利害关系的相关方（如第三人），不是我方也不回填。
    类别缺失（旧解析形态）才退回「法律地位 vs 代理何方」启发式。
    """
    groups: dict[str, list[dict[str, str]]] = {"client": [], "opponent": [], "co_party": [], "third": []}
    seen: set[str] = set(exclude_names)
    for conflict in conflicts:
        name = str(conflict.name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        item = {"name": name, "conflict_type": str(conflict.conflict_type or "").strip()}
        for field in ("category", "customer_type", "id_number", "phone"):
            value = str(getattr(conflict, field, "") or "").strip()
            if value:
                item[field] = value
        groups[_classify_conflict(item["conflict_type"], side, category=str(item.get("category") or ""))].append(item)
    return groups


def _classify_conflict(position: str, side: str, category: str = "") -> str:
    """按 OA 类别定阵营，类别缺失再按法律地位启发式。

    优先级：第三人/第三方类词（法律地位或类别）→ third；类别「对方当事人」→ opponent；
    类别「委托方」（非关联方）→ client；类别「委托方关联方」→ co_party；最后才看
    法律地位是否与代理何方相同（同位 = co_party，否则 opponent）。
    """
    compact_position = "".join(position.split())
    compact_category = "".join(category.split())
    if any(marker in compact_position for marker in _THIRD_PARTY_MARKERS):
        return "third"
    if compact_category:
        if any(marker in compact_category for marker in _THIRD_PARTY_MARKERS):
            return "third"
        if "对方" in compact_category:
            return "opponent"
        if "委托方" in compact_category and "关联" not in compact_category:
            return "client"
        if "关联" in compact_category:
            return "co_party"
    if side and compact_position and compact_position == side:
        return "co_party"
    return "opponent"


def _dedupe_customers(customers: list[OACaseCustomerData]) -> list[dict[str, str]]:
    """客户信息 tab 去重保序（按名称）；空名丢弃，空字段不输出。

    带上 OA 已有的证件号 / 电话 / 地址 / 法定代表人，供本地缺失时自动建库；
    自然人客户不写法定代表人字段（提取器会把「姓名」也当法定代表人）。
    """
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for customer in customers:
        name = str(getattr(customer, "name", "") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        client_type = str(getattr(customer, "customer_type", "") or "").strip()
        item: dict[str, str] = {"name": name, "customer_type": client_type}
        for field in ("id_number", "phone", "address"):
            value = _clean_field(getattr(customer, field, ""))
            if value:
                item[field] = value
        representative = _clean_field(getattr(customer, "legal_representative", ""))
        if representative and client_type != "natural":
            item["legal_representative"] = representative
        result.append(item)
    return result


def _clean_field(value: Any) -> str:
    """OA 空值常用「/」占位，建库时按空处理。"""
    text = str(value or "").strip()
    return "" if text in {"/", "-", "—", "无"} else text
