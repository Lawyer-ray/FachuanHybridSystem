"""律所ID 同步：OA 案件详情（OACaseData）→ 新建合同表单回填数据整形。

纯函数、无 ORM。admin 视图拿到 ScriptExecutorService 返回的 OACaseData 后，
经本模块整形成表单可直接消费的 JSON（合同类型枚举值 / ISO 日期 / 详情 URL /
当事人与律师名单）。当事人与律师只给名单，由前端经 admin autocomplete 做精确
匹配——新建页合同尚未保存，这里不落任何 Client / Lawyer 数据。
"""

from __future__ import annotations

from typing import Any

from apps.oa_filing.services.case_import_service import map_oa_case_type_from_text, parse_date
from apps.oa_filing.services.oa_data_models import OACaseData, OACaseInfoData

# 与 JTNAdapter.build_case_detail_url 同款（contracts 不可 import jtn 子包，此处独立维护）
_DETAIL_URL_TEMPLATE = (
    "https://ims.jtn.com/project/projectView.aspx?keyid={keyid}&FirstModel=PROJECT&SecondModel=PROJECT002"
)


def build_sync_payload(oa_data: OACaseData) -> dict[str, Any]:
    """OACaseData → 新建合同表单回填 JSON。

    合同类型沿用案件导入口径：案件类别优先、业务种类兜底；收案日期归一为
    ISO（解析不了给 None，前端跳过不填）。名单按名称去重保序。
    """
    info = oa_data.case_info
    keyid = str(oa_data.keyid or "").strip().lower()
    acceptance = parse_date(str(_text(info, "acceptance_date"))) if info else None
    case_number = _text(info, "case_no") or str(oa_data.case_no or "").strip()

    return {
        "guid": keyid,
        "detail_url": _DETAIL_URL_TEMPLATE.format(keyid=keyid) if keyid else "",
        "case_number": case_number,
        "name": _text(info, "case_name"),
        "case_type": _resolve_case_type(info),
        "start_date": acceptance.isoformat() if acceptance else None,
        "case_stage": _text(info, "case_stage"),
        "client_side": _text(info, "client_side"),
        "responsible_lawyer": _text(info, "responsible_lawyer"),
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
