"""
证据清单占位符服务

提供证据清单导出所需的占位符数据生成功能.
通过 ServiceLocator 注册为公共服务,供其他模块复用.

Requirements: 7.1, 7.2, 7.4
"""

from django.utils.translation import gettext_lazy as _
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from apps.core.exceptions import NotFoundError

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService


# 诉讼地位到显示名称的映射
# Requirements: 2.1, 2.2
LEGAL_STATUS_DISPLAY = {
    "plaintiff": "原告",
    "defendant": "被告",
    "third": "第三人",
    "applicant": "申请人",
    "respondent": "被申请人",
    "appellant": "上诉人",
    "appellee": "被上诉人",
    "criminal_defendant": "被告人",
    "orig_plaintiff": "原审原告",
    "orig_defendant": "原审被告",
    "orig_third": "原审第三人",
}

# 诉讼地位分组(用于排序)
# Requirements: 3.4
LEGAL_STATUS_ORDER = [
    "plaintiff",
    "applicant",
    "appellant",
    "defendant",
    "respondent",
    "appellee",
    "third",
    "criminal_defendant",
    "orig_plaintiff",
    "orig_defendant",
    "orig_third",
]


class EvidenceListPlaceholderService:
    """
    证据清单占位符服务

    负责生成证据清单导出所需的所有占位符数据,包括:
    - 证据清单名称
    - 当事人信息(简要)
    - 证据清单数据(表格循环)
    - 签名盖章信息

    Requirements: 7.1, 7.4
    """

    PLACEHOLDER_KEYS: ClassVar = [
        "证据清单名称",
        "当事人信息_简要",
        "证据清单",
        "证据清单签名盖章信息",
    ]

    def __init__(self, case_service: Optional["ICaseService"] = None) -> None:
        """
        初始化服务

        Args:
            case_service: 案件服务(可选,支持依赖注入)
        """
        self._case_service = case_service

    @property
    def case_service(self) -> "ICaseService":
        """
        获取案件服务(延迟加载)

        Returns:
            ICaseService 实例
        """
        if self._case_service is None:
            from apps.documents.services.wiring import get_case_service

            self._case_service = get_case_service()
        return self._case_service

    def get_evidence_list_context(self, evidence_list_id: int) -> dict[str, Any]:
        """
        获取证据清单导出的完整占位符上下文

        整合所有占位符生成方法,返回完整的上下文字典.

        Args:
            evidence_list_id: 证据清单 ID

        Returns:
            包含所有占位符的字典:
            - 证据清单名称: str
            - 当事人信息(简要): str
            - 证据清单: List[Dict]
            - 证据清单签名盖章信息: str

        Raises:
            NotFoundError: 证据清单不存在

        Requirements: 7.2
        """
        # 获取证据清单
        evidence_list = self._get_evidence_list(evidence_list_id)

        # 获取案件详细信息
        case_data = self._get_case_data(evidence_list.case_id)

        # 生成所有占位符
        # 注意:键名不能包含中文括号或特殊字符,否则 Jinja2 会解析错误
        context = {
            "证据清单名称": self.get_evidence_list_name(evidence_list, case_data),
            "当事人信息_简要": self.get_parties_brief(case_data),
            "证据清单": self.get_evidence_items(evidence_list),
            "证据清单签名盖章信息": self.get_signature_info(case_data),
        }

        return context

    def get_placeholder_keys(self) -> list[str]:
        return list(self.PLACEHOLDER_KEYS)

    def get_evidence_list_name(self, evidence_list: Any, case_data: dict[str, Any]) -> str:
        """
        生成证据清单名称占位符

        格式:「清单标题(我方诉讼地位)」
        - 多个诉讼地位用顿号分隔
        - 无我方当事人时仅返回清单标题

        Args:
            evidence_list: 证据清单实例
            case_data: 案件详细信息

        Returns:
            格式化的证据清单名称

        Requirements: 2.1, 2.2, 2.3, 2.4
        """
        title = evidence_list.title or ""

        # 获取我方当事人(is_our_client=True)
        parties = case_data.get("case_parties", [])
        our_parties = [p for p in parties if p.get("is_our_client")]

        # 无我方当事人时仅返回清单标题
        # Requirements: 2.4
        if not our_parties:
            return title

        # 提取唯一的诉讼地位(保持顺序)
        seen_statuses = set()
        unique_statuses: list[Any] = []
        for party in our_parties:
            legal_status = party.get("legal_status")
            if legal_status and legal_status not in seen_statuses:
                seen_statuses.add(legal_status)
                unique_statuses.append(legal_status)

        # 无诉讼地位时仅返回清单标题
        if not unique_statuses:
            return title

        # 转换为中文显示名称
        status_names: list[Any] = []
        for status in unique_statuses:
            display_name = LEGAL_STATUS_DISPLAY.get(status)
            if display_name:
                status_names.append(display_name)

        # 无有效诉讼地位时仅返回清单标题
        if not status_names:
            return title

        # 多个诉讼地位用顿号分隔
        # Requirements: 2.2, 2.3
        status_str = "、".join(status_names)

        # 返回格式:「清单标题(诉讼地位)」
        # Requirements: 2.1
        return f"{title}({status_str})"

    def get_parties_brief(self, case_data: dict[str, Any]) -> str:
        """生成当事人信息(简要)占位符"""
        parties = case_data.get("case_parties", [])
        if not parties:
            return ""

        groups = self._group_parties_by_status(parties)
        if not groups:
            return ""

        lines = self._format_ordered_groups(groups)
        return "\n".join(lines)

        for party in parties:
            legal_status = party.get("legal_status")
            name = party.get("client_name") or party.get("name", "")
            if not legal_status or not name:
                continue
            groups.setdefault(legal_status, []).append(name)
        return groups

        seen_statuses: set[str] = set()
        for status in LEGAL_STATUS_ORDER:
            if status not in groups:
                continue
            display_name = LEGAL_STATUS_DISPLAY.get(status)
            if not display_name:
                continue
            lines.append(f"{display_name}:{'、'.join(groups[status])}")
            seen_statuses.add(status)

        for status, names_list in groups.items():
            if status in seen_statuses:
                continue
            display_name = LEGAL_STATUS_DISPLAY.get(status, status)
            lines.append(f"{display_name}:{'、'.join(names_list)}")
        return lines

    def get_evidence_items(self, evidence_list: Any) -> list[dict[str, Any]]:
        """
        生成证据清单数据列表

        返回包含序号、证据名称、证明内容、页码的列表,
        用于 docxtpl 表格行循环.

        Args:
            evidence_list: 证据清单实例

        Returns:
            证据清单数据列表,每项包含:
            - 序号: int(全局连续序号)
            - 证据名称: str
            - 证明内容: str
            - 页码: str(page_range_display 格式)

        Requirements: 4.1, 4.2, 4.3, 4.4
        """
        # 获取该清单的所有证据明细,按序号排序
        items = evidence_list.items.all().order_by("order")

        # 边界情况:无证据明细
        # Requirements: 4.4
        if not items.exists():
            return []

        # 获取清单的起始序号(跨清单累计)
        # Requirements: 4.2
        start_order = evidence_list.start_order

        # 构建证据清单数据列表
        # Requirements: 4.1, 4.3
        result: list[Any] = []
        for item in items:
            # 计算全局连续序号
            # item.order 是清单内序号(从 1 开始)
            # 全局序号 = 起始序号 + 清单内序号 - 1
            global_order = start_order + item.order - 1

            result.append(
                {
                    "序号": global_order,
                    "证据名称": item.name or "",
                    "证明内容": item.purpose or "",
                    "页码": item.page_range_display,
                }
            )

        return result

    def get_signature_info(self, case_data: dict[str, Any]) -> str:
        """
        生成签名盖章信息占位符

        列出所有我方当事人的签名盖章信息:
        - 法人:「诉讼地位(盖章):名称」+「法定代表人(签名):姓名」+「日期:指定日期」
        - 自然人:「诉讼地位(签名+指模):名称」+「日期:指定日期」

        Args:
            case_data: 案件详细信息

        Returns:
            格式化的签名盖章信息

        Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
        """
        # 获取我方当事人(is_our_client=True)
        # Requirements: 5.1
        parties = case_data.get("case_parties", [])
        our_parties = [p for p in parties if p.get("is_our_client")]

        # 边界情况:无我方当事人
        if not our_parties:
            return ""

        # 获取案件指定日期并格式化为中文日期
        # Requirements: 5.4, 5.5
        specified_date_raw = case_data.get("specified_date") or ""
        specified_date = self._format_chinese_date(specified_date_raw)

        # 构建每个当事人的签名盖章信息
        party_blocks: list[Any] = []
        for party in our_parties:
            legal_status = party.get("legal_status")
            # 兼容 client_name 和 name 两种字段名
            name = party.get("client_name") or party.get("name", "")
            client_type = party.get("client_type", "")
            legal_representative = party.get("legal_representative", "")

            # 获取诉讼地位的中文显示名称
            status_display = LEGAL_STATUS_DISPLAY.get(legal_status, legal_status or "")

            # 跳过无效数据
            if not status_display or not name:
                continue

            lines: list[Any] = []

            if client_type == "legal":
                # 法人格式
                # Requirements: 5.2
                # Line 1: 「诉讼地位(盖章):名称」
                lines.append(f"{status_display}(盖章):{name}")
                # Line 2: 「法定代表人(签名):法定代表人姓名」
                lines.append(f"法定代表人(签名):{legal_representative}")
                # Line 3: 「日期:指定日期」
                lines.append(f"日期:{specified_date}")
            else:
                # 自然人格式(默认)
                # Requirements: 5.3
                # Line 1: 「诉讼地位(签名+指模):名称」
                lines.append(f"{status_display}(签名+指模):{name}")
                # Line 2: 「日期:指定日期」
                lines.append(f"日期:{specified_date}")

            party_blocks.append("\n".join(lines))

        # 每个当事人信息之间用空行分隔
        return "\n\n".join(party_blocks)

    def _get_evidence_list(self, evidence_list_id: int) -> Any:
        """
        获取证据清单

        Args:
            evidence_list_id: 证据清单 ID

        Returns:
            EvidenceList 实例

        Raises:
            NotFoundError: 证据清单不存在
        """
        from apps.documents.models import EvidenceList

        try:
            return EvidenceList.objects.select_related("case").get(id=evidence_list_id)
        except EvidenceList.DoesNotExist:
            raise NotFoundError(
                message=_("证据清单不存在"),
                code="EVIDENCE_LIST_NOT_FOUND",
                errors={"list_id": f"ID 为 {evidence_list_id} 的证据清单不存在"},
            ) from None

    def _get_case_data(self, case_id: int) -> dict[str, Any]:
        """
        获取案件详细信息

        Args:
            case_id: 案件 ID

        Returns:
            案件详细信息字典

        Raises:
            NotFoundError: 案件不存在
        """
        case_data = self.case_service.get_case_with_details_internal(case_id)
        if case_data is None:
            raise NotFoundError(
                message=_("案件不存在"),
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {case_id} 的案件不存在"},
            )
        return case_data

    def _format_chinese_date(self, date_str: str) -> str:
        """
        将日期字符串格式化为中文日期格式

        Args:
            date_str: 日期字符串(YYYY-MM-DD 格式)

        Returns:
            中文日期格式(YYYY年MM月DD日)
        """
        if not date_str:
            return ""

        try:
            from datetime import datetime

            # 解析日期字符串
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            # 格式化为中文日期
            return f"{dt.year}年{dt.month:02d}月{dt.day:02d}日"
        except (ValueError, TypeError):
            # 解析失败,返回原字符串
            return date_str
