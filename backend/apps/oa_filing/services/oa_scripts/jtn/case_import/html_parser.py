"""金诚同达 OA 案件导入 - HTML 解析 (纯函数)."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from lxml import html as lxml_html

from .models import OACaseCustomerData, OACaseData, OACaseInfoData, OAConflictData, OAListCaseCandidate

logger = logging.getLogger("apps.oa_filing.jtn_case_import")

_CASE_LIST_URL = "https://ims.jtn.com/project/index.aspx?FirstModel=PROJECT&SecondModel=PROJECT002"
_BASE_URL = "https://ims.jtn.com/project"
_DETAIL_URL_TEMPLATE = "{base}/projectView.aspx?keyid={keyid}&FirstModel=PROJECT&SecondModel=PROJECT002"


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    compact = str(value).replace("\xa0", " ").replace("　", " ")
    return re.sub(r"\s+", " ", compact).strip()


def normalize_label(value: str | None) -> str:
    text = normalize_text(value)
    return text.replace("：", "").replace(":", "").replace(" ", "")


def extract_row_cells_text(row_node: Any) -> list[str]:
    cells = row_node.xpath("./td")
    return [normalize_text("".join(cell.itertext())) for cell in cells]


def iter_label_value_pairs(cell_texts: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for idx in range(0, len(cell_texts) - 1, 2):
        label = normalize_label(cell_texts[idx])
        value = normalize_text(cell_texts[idx + 1])
        pairs.append((label, value))
    return pairs


def extract_hidden_input(html_text: str, name: str) -> str:
    pattern = re.compile(
        rf'<input[^>]+name=["\']{re.escape(name)}["\'][^>]*value=["\']([^"\']*)["\']',
        re.IGNORECASE,
    )
    match = pattern.search(html_text)
    return match.group(1).strip() if match else ""


def extract_case_no_from_text(row_text: str) -> str:
    text = normalize_text(row_text)
    if not text:
        return ""

    patterns = [
        r"(?<![A-Za-z0-9])\d{4}[A-Za-z]{1,8}\d{2,}(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])[A-Za-z]{1,4}\d{4,}(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])\d{6,}(?![A-Za-z0-9])",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return str(match.group(0)).strip()
    return ""


def extract_keyid_from_href(href: str) -> str | None:
    if not href:
        return None
    full_url = urljoin(_CASE_LIST_URL, href)
    query = parse_qs(urlparse(full_url).query)
    keyid = query.get("keyid", query.get("KeyID", [None]))[0]
    return str(keyid).strip() if keyid else None


def score_case_name_cell(cell_text: str, *, case_no: str) -> int:
    text = normalize_text(cell_text)
    if not text:
        return -100
    if text.isdigit():
        return -90
    if text in {"查看", "编辑", "删除", "详情", "操作"}:
        return -80

    score = 0
    if case_no and case_no in text:
        score += 30
    if "诉" in text:
        score += 20
    if any(marker in text for marker in ("纠纷", "案件", "案【", "案[", "申请")):
        score += 12
    if any(marker in text for marker in ("[诉讼]", "民商事案件", "已完善", "信息完善", "在办中", "推送至社区")):
        score -= 15
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        score -= 20
    if len(text) <= 2:
        score -= 10
    return score


def clean_case_name_text(value: str, *, case_no: str) -> str:
    text = normalize_text(value)
    if not text:
        return ""

    if case_no and case_no in text:
        text = text.replace(case_no, " ")

    for marker in ("查看", "编辑", "删除", "详情", "操作"):
        text = text.replace(marker, " ")

    for marker in (
        "[诉讼]",
        "[非诉]",
        "民商事案件",
        "刑事案件",
        "行政案件",
        "已完善",
        "信息完善",
        "在办中",
        "修改承办律师",
        "利冲变更申请",
        "法院进程变更",
        "保全信息变更",
        "多地合作变更申请",
        "对外合办变更申请",
        "案件负责人变更申请",
        "零收费变更申请",
        "添加案件进程信息",
        "添加工作日志审批人",
        "上传定稿合同",
        "取消推送至社区",
        "推送至社区",
        "已推业绩",
        "撤销推送",
    ):
        if marker in text:
            text = text.split(marker, 1)[0].strip()

    text = re.sub(r"^(?:正\s*式|更多)\s+", "", text)
    text = re.sub(r"^([一-龥A-Za-z·]{2,16})\s+(?=\1诉)", "", text)
    text = re.sub(r"^\d+\s+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_case_name_from_row(row_node: Any, *, case_no: str, row_text: str) -> str:
    best_text = ""
    best_score = -10_000

    for cell_text in extract_row_cells_text(row_node):
        score = score_case_name_cell(cell_text, case_no=case_no)
        if score > best_score:
            best_score = score
            best_text = cell_text

    cleaned = clean_case_name_text(best_text, case_no=case_no)
    if cleaned:
        return cleaned
    return clean_case_name_text(row_text, case_no=case_no)


def extract_case_candidates_from_search_html(html_text: str) -> list[OAListCaseCandidate]:
    candidates: list[OAListCaseCandidate] = []
    seen_keys: set[tuple[str, str]] = set()
    try:
        root = lxml_html.fromstring(html_text)
        for row in root.xpath("//tr"):
            links = row.xpath('.//a[contains(@href, "projectView.aspx") and contains(@href, "keyid=")]')
            if not links:
                continue
            cell_texts = extract_row_cells_text(row)
            row_text = normalize_text(" ".join(cell_texts))
            case_no = extract_case_no_from_text(row_text)

            for link in links:
                href = str(link.get("href") or "")
                keyid = extract_keyid_from_href(href)
                if not keyid:
                    continue

                case_name = normalize_text("".join(link.itertext()))
                if case_name in {"查看", "编辑", "删除", "详情", "操作"}:
                    case_name = ""
                if not case_name:
                    case_name = extract_case_name_from_row(
                        row,
                        case_no=case_no,
                        row_text=row_text,
                    )

                unique_key = (keyid, case_no)
                if unique_key in seen_keys:
                    continue
                seen_keys.add(unique_key)

                candidates.append(
                    OAListCaseCandidate(
                        case_no=case_no,
                        case_name=case_name,
                        keyid=keyid,
                        detail_url=_DETAIL_URL_TEMPLATE.format(base=_BASE_URL, keyid=keyid),
                    )
                )
    except Exception:
        logger.debug("解析按名称查询结果失败", exc_info=True)

    return candidates


def extract_case_keyid_from_search_html(*, html_text: str, case_no: str) -> str | None:
    """从查询结果 HTML 中解析案件 keyid。"""
    try:
        root = lxml_html.fromstring(html_text)
        for row in root.xpath("//tr"):
            row_text = normalize_text("".join(row.itertext()))
            if case_no not in row_text:
                continue
            links = row.xpath('.//a[contains(@href, "projectView.aspx") and contains(@href, "keyid=")]')
            for link in links:
                href = str(link.get("href") or "")
                keyid = extract_keyid_from_href(href)
                if keyid:
                    return keyid
    except Exception:
        logger.debug("lxml 解析查询结果失败，回退正则匹配: %s", case_no, exc_info=True)

    escaped_case_no = re.escape(case_no)
    regex = re.compile(
        rf"{escaped_case_no}[\s\S]{{0,5000}}?projectView\.aspx\?keyid=([^&'\" >]+)",
        re.IGNORECASE,
    )
    match = regex.search(html_text)
    if match:
        return match.group(1)
    return None


def parse_case_detail_html(
    *,
    html_text: str,
    case_no: str,
    keyid: str,
) -> OACaseData | None:
    """解析案件详情 HTML（客户信息 + 案件信息 + 利冲 + 委托合同收费）。"""
    try:
        root = lxml_html.fromstring(html_text)
        customers = extract_customers_from_html(root)
        case_info = extract_case_info_from_html(root, fallback_case_no=case_no)
        _apply_fee_info(case_info, extract_fee_info_from_html(root))
        conflicts = extract_conflicts_from_html(root)
        return OACaseData(
            case_no=case_no,
            keyid=keyid,
            customers=customers,
            case_info=case_info,
            conflicts=conflicts,
        )
    except Exception as exc:
        logger.warning("解析案件详情HTML异常 %s: %s", case_no, exc)
        return None


def extract_customers_from_html(root: Any) -> list[OACaseCustomerData]:
    customers: list[OACaseCustomerData] = []
    rows = root.xpath('//div[@id="tab_con_1"]//tr')
    current_customer: OACaseCustomerData | None = None

    for row in rows:
        cell_texts = extract_row_cells_text(row)
        if not cell_texts:
            continue

        row_text = normalize_text(" ".join(cell_texts))
        name_match = re.search(r"客户（([^）]+)）信息", row_text)
        if name_match:
            if current_customer and current_customer.name:
                customers.append(current_customer)

            customer_name = normalize_text(name_match.group(1))
            customer_type = "legal" if ("企业" in row_text or "公司" in customer_name) else "natural"
            current_customer = OACaseCustomerData(name=customer_name, customer_type=customer_type)
            continue

        if current_customer is None:
            continue

        for label, value in iter_label_value_pairs(cell_texts):
            if not label:
                continue
            if "客户类型" in label and value:
                current_customer.customer_type = "legal" if "企业" in value or "公司" in value else "natural"
            elif "身份证" in label and value:
                current_customer.id_number = value
            elif "地址" in label and value:
                current_customer.address = value
            elif ("法定代表" in label or "负责人" in label) and value:
                current_customer.legal_representative = value
            elif "行业" in label and value:
                current_customer.industry = value
            elif ("电话" in label or "号码" in label) and value:
                current_customer.phone = value

    if current_customer and current_customer.name:
        customers.append(current_customer)

    return customers


def extract_case_info_from_html(root: Any, *, fallback_case_no: str) -> OACaseInfoData:
    case_info = OACaseInfoData(case_no=fallback_case_no)
    rows = root.xpath('//div[@id="tab_con_2"]//tr')

    for row in rows:
        cell_texts = extract_row_cells_text(row)
        if len(cell_texts) < 2:
            continue

        for label, value in iter_label_value_pairs(cell_texts):
            if not label:
                continue
            if "案件名称" in label and value:
                case_info.case_name = value
            elif "案件阶段" in label and value:
                case_info.case_stage = value
            elif "收案日期" in label and value:
                case_info.acceptance_date = value
            elif ("案件类别" in label or "案件类型" in label) and value:
                case_info.case_category = value
            elif "业务种类" in label and value:
                case_info.case_type = value
            elif "案件负责人" in label and value:
                case_info.responsible_lawyer = value
            elif "案情简介" in label and value:
                case_info.description = value[:500]
            elif "代理何方" in label and value:
                case_info.client_side = value
            elif "案件编号" in label and value:
                case_info.case_no = value

    return case_info


def extract_conflicts_from_html(root: Any) -> list[OAConflictData]:
    """解析利冲 tab：真实 OA 为列式表（分组标题 + 表头 + 数据行），兼容旧键值对结构。

    真实结构（2026-10-19 实测）：每个分组一张表，表前单格行「▼类别：对方当事人　　法律地位：被告」，
    表头「序号|客户类型|中文名称|英文名称|联系人|身份证号码|联系电话|付款方」，数据行按列取值；
    conflict_type 取分组「法律地位」（被告 / 原审第三人…），缺失退回该行「客户类型」列（机关 / 自然人）；
    category 取分组「类别」（委托方 / 委托方关联方 / 对方当事人），行级另带客户类型映射、证件号与电话。
    旧键值对结构（「中文名称|X」「法律地位|Y」成对逐行）保持原行为，供其他形态/夹具使用。
    """
    conflicts: list[OAConflictData] = []
    rows = root.xpath('//div[@id="tab_con_3"]//tr')

    group_position: str | None = None
    group_category: str | None = None
    name_col: int | None = None
    type_col: int | None = None
    id_col: int | None = None
    phone_col: int | None = None
    kv_name: str | None = None
    kv_type: str | None = None
    kv_category: str | None = None
    kv_id_number: str | None = None
    kv_phone: str | None = None

    def _flush_kv() -> None:
        if not kv_name:
            return
        conflicts.append(
            OAConflictData(
                name=kv_name,
                conflict_type=kv_type,
                category=kv_category,
                id_number=kv_id_number,
                phone=kv_phone,
            )
        )

    for row in rows:
        cell_texts = extract_row_cells_text(row)
        if not cell_texts:
            continue

        # 分组标题行（单格含「类别：」）：记录本组类别与法律地位，重置列映射
        if len(cell_texts) == 1 and "类别" in cell_texts[0]:
            title = normalize_text(cell_texts[0])
            position_match = _CONFLICT_GROUP_POSITION_RE.search(title)
            group_position = normalize_text(position_match.group(1)) if position_match else ""
            group_position = group_position or None
            category_match = _CONFLICT_GROUP_CATEGORY_RE.search(title)
            group_category = normalize_text(category_match.group(1)) if category_match else ""
            group_category = group_category or None
            name_col = type_col = id_col = phone_col = None
            continue

        labels = [normalize_label(cell) for cell in cell_texts]
        if sum(1 for label in labels if label in _CONFLICT_TABLE_HEADERS) >= 3:
            name_col = labels.index("中文名称") if "中文名称" in labels else None
            type_col = labels.index("客户类型") if "客户类型" in labels else None
            id_col = labels.index("身份证号码") if "身份证号码" in labels else None
            phone_col = labels.index("联系电话") if "联系电话" in labels else None
            continue

        if name_col is not None:
            conflict = _conflict_from_columnar_row(
                cell_texts,
                name_col=name_col,
                type_col=type_col,
                id_col=id_col,
                phone_col=phone_col,
                group_position=group_position,
                group_category=group_category,
            )
            if conflict is not None:
                conflicts.append(conflict)
            continue

        # 旧键值对结构
        for label, value in iter_label_value_pairs(cell_texts):
            if not label:
                continue
            if "中文名称" in label and value:
                _flush_kv()
                kv_name = value
                kv_type = kv_category = kv_id_number = kv_phone = None
            elif "类别" in label and value:
                kv_category = value
            elif ("法律地位" in label and value) or (
                "类型" in label and "客户类型" not in label and "法律地位" not in label and value
            ):
                kv_type = value
            elif "身份证" in label and value:
                kv_id_number = value
            elif ("电话" in label or "号码" in label) and value:
                kv_phone = value

    _flush_kv()

    return conflicts


# 利冲列式表的表头列名（真实 OA 结构）；一行命中 ≥3 个即判定为表头行
_CONFLICT_TABLE_HEADERS = frozenset(
    {"序号", "客户类型", "中文名称", "英文名称", "联系人", "身份证号码", "联系电话", "付款方"}
)
# 分组标题「▼类别：对方当事人　　法律地位：被告　　…」分别提取类别与法律地位
_CONFLICT_GROUP_POSITION_RE = re.compile(r"法律地位[：:]\s*(\S+)")
_CONFLICT_GROUP_CATEGORY_RE = re.compile(r"类别[：:]\s*(\S+)")


def _conflict_from_columnar_row(
    cell_texts: list[str],
    *,
    name_col: int,
    type_col: int | None,
    id_col: int | None = None,
    phone_col: int | None = None,
    group_position: str | None = None,
    group_category: str | None = None,
) -> OAConflictData | None:
    """列式数据行取一条利冲：名称列空 / 仍是列名（无数据的表头复读）返回 None。"""

    def _cell(col: int | None) -> str:
        if col is None or len(cell_texts) <= col:
            return ""
        return normalize_text(cell_texts[col])

    name = _cell(name_col)
    if not name or name in _CONFLICT_TABLE_HEADERS:
        return None
    row_type = _cell(type_col)
    return OAConflictData(
        name=name,
        conflict_type=group_position or row_type or None,
        category=group_category,
        customer_type=_customer_type_from_oa_label(row_type),
        id_number=_cell(id_col) or None,
        phone=_cell(phone_col) or None,
    )


def _customer_type_from_oa_label(text: str) -> str | None:
    """OA「客户类型」列（企业 / 机关 / 自然人…）→ 本地 client_type；空 / 认不出给 None。"""
    if not text:
        return None
    if "自然人" in text:
        return "natural"
    return "legal"


# 委托合同信息 tab（tab_con_5）的收费标签 → 数据键
_FEE_LABEL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fee_mode", ("收费方式",)),
    ("fee_amount", ("合同总额", "合同金额")),
    ("fee_currency", ("币种",)),
    ("fee_waived", ("是否免费或减免代理", "免费或减免")),
)


def _match_fee_key(label: str) -> str | None:
    for key, keywords in _FEE_LABEL_RULES:
        if any(keyword in label for keyword in keywords):
            return key
    return None


def extract_fee_info_from_html(root: Any) -> dict[str, str]:
    """解析委托合同信息 tab（tab_con_5）的收费键值对。

    首表是「标签：| 值 | 标签：| 值」行（收费方式 / 合同总额 / 币种 / 是否免费或减免代理）；
    同 tab 下方还有发票 / 收款列表，列名与这几个标签不冲突。返回键：
    fee_mode / fee_amount / fee_currency / fee_waived，未命中键不出现。
    """
    result: dict[str, str] = {}
    for row in root.xpath('//div[@id="tab_con_5"]//tr'):
        cell_texts = extract_row_cells_text(row)
        if len(cell_texts) < 2:
            continue
        for label, value in iter_label_value_pairs(cell_texts):
            key = _match_fee_key(label) if label and value else None
            if key and key not in result:
                result[key] = value
    return result


def _apply_fee_info(case_info: OACaseInfoData, fee: dict[str, str]) -> None:
    """把委托合同 tab 的收费键值挂到 case_info（OA 未填的键保持 None）。"""
    case_info.fee_mode_text = fee.get("fee_mode") or None
    case_info.fee_amount_text = fee.get("fee_amount") or None
    case_info.fee_currency = fee.get("fee_currency") or None
    case_info.fee_waived = fee.get("fee_waived") or None
