"""
归档占位符服务

提供归档文书所需的占位符生成,包括案件基本信息、合同信息、
日期信息和日志汇总等.
"""

import logging
from datetime import date
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


class _ArchiveMaterialsRichText:
    """结案归档材料文本，支持 docxtpl 硬换行渲染和预览文本显示。

    继承 docxtpl.RichText 使 docxtpl 在渲染时正确识别并内联 XML，
    而不是将 XML 作为纯文本嵌入 <w:t> 标签。
    plain_text 属性供预览服务使用。
    """

    def __init__(self) -> None:
        from docxtpl import RichText

        self._rt = RichText()
        self._text_parts: list[str] = []

    def add_break(self) -> None:
        """添加硬换行 (w:br)"""
        self._rt.xml += '<w:r><w:br/></w:r>'
        self._text_parts.append("\n")

    def add(self, text: str) -> None:
        """添加文本行"""
        from xml.sax.saxutils import escape

        escaped = escape(text)
        self._rt.xml += f'<w:r><w:t xml:space="preserve">{escaped}</w:t></w:r>'
        self._text_parts.append(text)

    @property
    def plain_text(self) -> str:
        """纯文本供预览使用"""
        return "".join(self._text_parts)

    def __str__(self) -> str:
        """返回 XML 供 docxtpl 渲染内联（docxtpl 识别 RichText 实例）"""
        return self._rt.xml


@PlaceholderRegistry.register
class ArchivePlaceholderService(BasePlaceholderService):
    """归档文书占位符服务"""

    name: str = "archive_placeholder_service"
    display_name: str = "归档文书占位符服务"
    description: str = "提供归档文书所需的占位符(案件/合同/日期/日志信息)"
    category: str = "archive"
    placeholder_keys: ClassVar = [
        "主办律师姓名",
        "合同名称",
        "合同我方当事人名称",
        "合同对方当事人名称",
        "合同类型",
        "律所OA案件编号",
        "案件案号",
        "管辖法院",
        "案件当前阶段",
        "案件审理结果",
        "办案小结内容",
        "律师工作日志内容",
        "归档日期",
        "生成日期",
        "结案归档材料",
        "卷内目录",
    ]
    placeholder_metadata: ClassVar[dict[str, dict[str, Any]]] = {
        "主办律师姓名": {
            "display_name": "主办律师姓名",
            "description": "案件主办律师的真实姓名",
            "example_value": "张律师",
        },
        "合同名称": {
            "display_name": "合同名称",
            "description": "关联合同的名称",
            "example_value": "某某公司诉某某公司合同纠纷",
        },
        "合同我方当事人名称": {
            "display_name": "合同我方当事人名称",
            "description": "合同中我方(委托方)当事人名称,顿号分隔",
            "example_value": "某某有限公司、张某",
        },
        "合同对方当事人名称": {
            "display_name": "合同对方当事人名称",
            "description": "合同中对方当事人名称,顿号分隔",
            "example_value": "某某银行股份有限公司",
        },
        "合同类型": {
            "display_name": "合同类型",
            "description": "合同类型的中文显示名",
            "example_value": "民商事",
        },
        "律所OA案件编号": {
            "display_name": "律所OA案件编号",
            "description": "律所OA系统中的案件编号",
            "example_value": "2026GZM0001",
        },
        "案件案号": {
            "display_name": "案件案号",
            "description": "案件在法院的案号(首个生效案号)",
            "example_value": "(2026)粤0606民初0001号",
        },
        "管辖法院": {
            "display_name": "管辖法院",
            "description": "案件审理法院名称",
            "example_value": "某某市某某区人民法院",
        },
        "案件当前阶段": {
            "display_name": "案件当前阶段",
            "description": "案件当前审理阶段(如一审、二审等)",
            "example_value": "一审",
        },
        "案件审理结果": {
            "display_name": "案件审理结果",
            "description": "案件裁判文书中的判决/调解主文内容",
            "example_value": "一、被告某某公司于本判决生效之日起十日内向原告支付欠款100万元...",
        },
        "办案小结内容": {
            "display_name": "办案小结内容",
            "description": "办案小结正文内容，优先使用案件审理结果，无审理结果时根据合同名称和当事人生成",
            "example_value": "本案为某某公司诉某某公司合同纠纷。本所受某某有限公司提供法律服务。在服务期间，我们在公司领导的指导下，与各位同事积极配合，顺利的完成了公司的各项法律服务工作。",
        },
        "律师工作日志内容": {
            "display_name": "律师工作日志内容",
            "description": "案件进展日志汇总，格式为日期+描述，排除自动捕获的短信/文书送达日志，硬换行分隔",
            "example_value": "2026年3月10日，签订委托代理合同\n2026年4月15日，一审开庭",
        },
        "归档日期": {
            "display_name": "归档日期",
            "description": "归档操作日期(中文格式)",
            "example_value": "2026年04月19日",
        },
        "生成日期": {
            "display_name": "生成日期",
            "description": "文档生成日期(中文格式)",
            "example_value": "2026年04月19日",
        },
        "结案归档材料": {
            "display_name": "结案归档材料",
            "description": "已完成的归档检查项材料目录，按序号排列，硬换行分隔",
            "example_value": "1.委托代理合同、风险告知书\n2.收费凭证\n3.律师办案工作日记",
        },
        "卷内目录": {
            "display_name": "卷内目录",
            "description": "卷内目录表格数据列表，每项含序号、材料名称、页码",
            "example_value": '[{"序号": 1, "材料名称": "委托代理合同", "页码": "1-3"}]',
        },
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成归档文书占位符

        Args:
            context_data: 包含 case/contract 等数据的上下文

        Returns:
            包含归档占位符键值对的字典
        """
        result: dict[str, Any] = {}
        case = context_data.get("case")
        contract = context_data.get("contract")

        today_str = self._format_chinese_date(date.today())

        # {{归档日期}} / {{生成日期}} — 当前日期
        result["归档日期"] = today_str
        result["生成日期"] = today_str

        # 从 contract 获取合同相关字段
        if contract:
            result["合同名称"] = self._get_contract_name(contract)
            result["合同类型"] = self._get_contract_type(contract)
            result["合同我方当事人名称"] = self._get_our_party_names(contract)
            result["律所OA案件编号"] = self._get_oa_case_number(contract)

            # 合同对方当事人：先从合同当事人找，找不到则从关联回案件找
            opposing = self._get_opposing_party_names(contract)
            if not opposing and case:
                opposing = self._get_opposing_party_names_from_case(case)
            result["合同对方当事人名称"] = opposing

        # 主办律师姓名：优先从 case 获取，回退到 contract.assignments
        if case:
            result["主办律师姓名"] = self._get_lead_lawyer_name(case)
        elif contract:
            result["主办律师姓名"] = self._get_lead_lawyer_name_from_contract(contract)

        # 从 case 获取案件相关字段
        if case:
            result["案件案号"] = self._get_case_number(case)
            result["管辖法院"] = self._get_court_name(case)
            result["案件当前阶段"] = self._get_case_stage(case)
            result["案件审理结果"] = self._get_trial_result(case)

        # 办案小结内容：优先使用案件审理结果，无结果时根据合同名称和当事人生成
        result["办案小结内容"] = self._get_case_summary_content(case, contract, result)

        # 律师工作日志内容：从案件进展获取，排除自动捕获的短信/文书送达日志
        if case:
            result["律师工作日志内容"] = self._get_lawyer_work_log_content(case)

        # 结案归档材料：实时检测已完成的检查项，生成编号目录
        if contract:
            result["结案归档材料"] = self._get_archive_materials_list(contract)
            result["卷内目录"] = self._get_inner_catalog_items(contract)

        return result

    @staticmethod
    def _format_chinese_date(d: date) -> str:
        """格式化为中文日期"""
        return f"{d.year}年{d.month:02d}月{d.day:02d}日"

    @staticmethod
    def _get_contract_name(contract: Any) -> str:
        """获取合同名称"""
        return str(getattr(contract, "name", "") or "")

    @staticmethod
    def _get_contract_type(contract: Any) -> str:
        """获取合同类型中文显示名"""
        try:
            return contract.get_case_type_display() or ""
        except Exception:
            return str(getattr(contract, "case_type", "") or "")

    @staticmethod
    def _get_our_party_names(contract: Any) -> str:
        """获取合同我方当事人名称(顿号分隔)"""
        try:
            parties = contract.contract_parties.select_related("client").all()
        except Exception:
            logger.warning("获取合同当事人失败", extra={"contract_id": getattr(contract, "id", None)})
            return ""

        names: list[str] = []
        seen: set[str] = set()
        for party in parties:
            if getattr(party, "role", None) != "PRINCIPAL":
                continue
            client = getattr(party, "client", None)
            if not client:
                continue
            name = str(getattr(client, "name", "") or "").strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return "、".join(names)

    @staticmethod
    def _get_opposing_party_names(contract: Any) -> str:
        """获取合同对方当事人名称(顿号分隔)"""
        try:
            parties = contract.contract_parties.select_related("client").all()
        except Exception:
            logger.warning("获取合同当事人失败", extra={"contract_id": getattr(contract, "id", None)})
            return ""

        names: list[str] = []
        seen: set[str] = set()
        for party in parties:
            if getattr(party, "role", None) != "OPPOSING":
                continue
            client = getattr(party, "client", None)
            if not client:
                continue
            name = str(getattr(client, "name", "") or "").strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return "、".join(names)

    @staticmethod
    def _get_oa_case_number(contract: Any) -> str:
        """获取律所OA案件编号"""
        return str(getattr(contract, "law_firm_oa_case_number", "") or "")

    @staticmethod
    def _get_lead_lawyer_name_from_contract(contract: Any) -> str:
        """从合同指派记录获取主办律师姓名(is_primary=True 的第一个)"""
        try:
            assignment = contract.assignments.select_related("lawyer").filter(is_primary=True).first()
        except Exception:
            assignment = None

        if not assignment:
            # 兜底: 取第一个指派
            try:
                assignment = contract.assignments.select_related("lawyer").first()
            except Exception:
                logger.warning("获取合同主办律师失败", extra={"contract_id": getattr(contract, "id", None)})
                return ""

        if not assignment:
            return ""

        lawyer = getattr(assignment, "lawyer", None)
        if not lawyer:
            return ""

        return str(getattr(lawyer, "real_name", None) or getattr(lawyer, "username", "") or "")

    @staticmethod
    def _get_lead_lawyer_name(case: Any) -> str:
        """获取主办律师姓名(is_primary=True 的第一个)"""
        try:
            assignment = case.assignments.select_related("lawyer").filter(is_primary=True).first()
        except Exception:
            # 兼容旧字段: role='lead'
            try:
                assignment = case.assignments.select_related("lawyer").filter(role="lead").first()
            except Exception:
                assignment = None

        if not assignment:
            # 兜底: 取第一个指派
            try:
                assignment = case.assignments.select_related("lawyer").first()
            except Exception:
                logger.warning("获取主办律师失败", extra={"case_id": getattr(case, "id", None)})
                return ""

        if not assignment:
            return ""

        lawyer = getattr(assignment, "lawyer", None)
        if not lawyer:
            return ""

        return str(getattr(lawyer, "real_name", None) or getattr(lawyer, "username", "") or "")

    @staticmethod
    def _get_case_number(case: Any) -> str:
        """获取首个案件案号"""
        try:
            # 优先取已生效案号，其次取第一个案号
            cn = case.case_numbers.filter(is_active=True).first()
            if not cn:
                cn = case.case_numbers.first()
            if cn:
                return str(getattr(cn, "number", "") or "")
        except Exception:
            logger.warning("获取案件案号失败", extra={"case_id": getattr(case, "id", None)})
        return ""

    @staticmethod
    def _get_court_name(case: Any) -> str:
        """获取管辖法院名称(审理机构)"""
        try:
            authorities = case.supervising_authorities.filter(authority_type="trial")
            names: list[str] = []
            seen: set[str] = set()
            for auth in authorities:
                name = str(getattr(auth, "name", "") or "").strip()
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
            return "、".join(names)
        except Exception:
            logger.warning("获取管辖法院失败", extra={"case_id": getattr(case, "id", None)})
            return ""

    @staticmethod
    def _get_case_stage(case: Any) -> str:
        """获取案件当前阶段"""
        if not getattr(case, "current_stage", None):
            return ""
        try:
            return case.get_current_stage_display() or ""
        except Exception:
            return str(getattr(case, "current_stage", "") or "")

    @staticmethod
    def _get_trial_result(case: Any) -> str:
        """获取案件审理结果(首个案号的执行依据主文)"""
        try:
            # 优先取已生效案号，其次取第一个案号
            cn = case.case_numbers.filter(is_active=True).first()
            if not cn:
                cn = case.case_numbers.first()
            if cn:
                content = getattr(cn, "document_content", None) or ""
                return str(content).strip()
        except Exception:
            logger.warning("获取案件审理结果失败", extra={"case_id": getattr(case, "id", None)})
        return ""

    @staticmethod
    def _get_case_summary_content(
        case: Any, contract: Any, already_generated: dict[str, Any]
    ) -> str:
        """
        获取办案小结内容.

        优先使用已生成的{{案件审理结果}}内容;
        若案件审理结果为空,则根据合同名称和合同我方当事人名称生成模板文字.
        """
        # 1. 优先使用案件审理结果
        trial_result = already_generated.get("案件审理结果", "")
        if trial_result and str(trial_result).strip() and str(trial_result).strip() != "/":
            return str(trial_result).strip()

        # 2. 无审理结果时，根据合同名称和合同我方当事人名称生成
        contract_name = already_generated.get("合同名称", "")
        our_party_names = already_generated.get("合同我方当事人名称", "")

        if contract_name and str(contract_name).strip() and str(contract_name).strip() != "/":
            cn = str(contract_name).strip()
            party = str(our_party_names).strip() if our_party_names and str(our_party_names).strip() != "/" else "委托人"
            return f"本案为{cn}。本所受{party}提供法律服务。在服务期间，我们在公司领导的指导下，与各位同事积极配合，顺利的完成了公司的各项法律服务工作。"

        return ""

    # 自动捕获日志的内容前缀，用于识别并排除这些日志
    _AUTO_LOG_PREFIXES: ClassVar[tuple[str, ...]] = (
        "收到法院短信：",
        "收到法院短信:",
        "文书送达自动下载:",
        "文书送达自动下载：",
    )

    @classmethod
    def _is_auto_generated_log(cls, log: Any) -> bool:
        """判断日志是否为自动捕获生成（法院短信/文书送达自动下载等）"""
        content = str(getattr(log, "content", "") or "")
        return content.startswith(cls._AUTO_LOG_PREFIXES)

    @staticmethod
    def _get_lawyer_work_log_content(case: Any) -> str:
        """
        获取律师工作日志内容.

        从案件进展(CaseLog)中提取日志,排除自动捕获的短信/文书送达日志,
        格式为日期+描述,硬换行分隔.
        """
        try:
            logs = case.logs.select_related("actor").order_by("created_at")
        except Exception:
            logger.warning("获取案件日志失败", extra={"case_id": getattr(case, "id", None)})
            return ""

        lines: list[str] = []
        for log in logs:
            # 排除自动捕获的日志
            if ArchivePlaceholderService._is_auto_generated_log(log):
                continue
            content = str(getattr(log, "content", "") or "").strip()
            if not content:
                continue
            created_at = getattr(log, "created_at", None)
            if created_at:
                date_str = f"{created_at.year}年{created_at.month}月{created_at.day}日"
            else:
                date_str = "未知日期"
            lines.append(f"{date_str}，{content}")

        if not lines:
            return ""

        # 使用硬换行渲染
        rt = _ArchiveMaterialsRichText()
        for i, line in enumerate(lines):
            if i > 0:
                rt.add_break()
            rt.add(line)
        return rt

    @staticmethod
    def _get_opposing_party_names_from_case(case: Any) -> str:
        """从案件当事人中获取对方当事人名称(非我方当事人,顿号分隔)"""
        try:
            parties = case.parties.select_related("client").all()
        except Exception:
            logger.warning("获取案件当事人失败", extra={"case_id": getattr(case, "id", None)})
            return ""

        names: list[str] = []
        seen: set[str] = set()
        for party in parties:
            client = getattr(party, "client", None)
            if not client:
                continue
            # 非我方当事人即为对方
            if getattr(client, "is_our_client", False):
                continue
            name = str(getattr(client, "name", "") or "").strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return "、".join(names)

    @staticmethod
    def _get_archive_materials_list(contract: Any) -> str:
        """
        生成结案归档材料目录。

        实时检测归档检查清单中已完成的项，从"委托合同"项开始，
        按检查清单序号排列，跳过案卷封面/结案归档登记表/案卷目录，
        生成编号列表（硬换行分隔）。
        """
        from apps.contracts.services.archive.checklist_service import ArchiveChecklistService

        checklist_service = ArchiveChecklistService()
        checklist = checklist_service.get_checklist_with_status(contract)

        items = checklist.get("items", [])

        # 需要跳过的检查项（案卷封面/结案归档登记表/案卷目录 本身就是归档文书，不是材料目录）
        skip_codes = {"nl_1", "nl_2", "nl_3", "lt_1", "lt_2", "lt_3", "cr_1", "cr_2", "cr_3"}
        # 也跳过模板前缀为 1/2/3 的code
        skip_templates = {"case_cover", "closing_archive_register", "inner_catalog"}

        lines: list[str] = []
        seq = 1

        for item in items:
            code = item.get("code", "")
            template = item.get("template")
            name = item.get("name", "")
            completed = item.get("completed", False)

            # 跳过封面/登记表/目录
            if code in skip_codes or template in skip_templates:
                continue

            # 只包含已完成的项
            if not completed:
                continue

            lines.append(f"{seq}.{name}")
            seq += 1

        if not lines:
            return ""

        # 硬换行（docx 中的 shift+enter）
        # 使用 docxtpl.RichText 的 add_break() 方法实现硬换行
        from docxtpl import RichText

        rt = _ArchiveMaterialsRichText()
        for i, line in enumerate(lines):
            if i > 0:
                rt.add_break()  # 硬换行 (shift+enter)
            rt.add(line)
        return rt

    @staticmethod
    def _get_inner_catalog_items(contract: Any) -> list[dict[str, Any]]:
        """
        生成卷内目录表格数据。

        实时检测归档检查清单中已完成的项，跳过案卷封面/登记表/目录，
        对每项材料计算页码范围。

        Returns:
            [{"序号": int, "材料名称": str, "页码": str}, ...]
        """
        from apps.contracts.services.archive.checklist_service import ArchiveChecklistService

        checklist_service = ArchiveChecklistService()
        checklist = checklist_service.get_checklist_with_status(contract)

        items = checklist.get("items", [])

        # 需要跳过的检查项
        skip_codes = {"nl_1", "nl_2", "nl_3", "lt_1", "lt_2", "lt_3", "cr_1", "cr_2", "cr_3"}
        skip_templates = {"case_cover", "closing_archive_register", "inner_catalog"}

        catalog_items: list[dict[str, Any]] = []
        seq = 1
        current_page = 1

        for item in items:
            code = item.get("code", "")
            template = item.get("template")
            name = item.get("name", "")
            completed = item.get("completed", False)
            material_ids = item.get("material_ids", [])

            # 跳过封面/登记表/目录
            if code in skip_codes or template in skip_templates:
                continue

            # 只包含已完成的项
            if not completed:
                continue

            # 计算该材料的页数
            page_count = ArchivePlaceholderService._calculate_material_page_count(
                contract, code, material_ids
            )

            # 计算页码范围
            if page_count > 0:
                page_start = current_page
                page_end = current_page + page_count - 1
                if page_start == page_end:
                    page_range = str(page_start)
                else:
                    page_range = f"{page_start}-{page_end}"
                current_page = page_end + 1
            else:
                page_range = "-"

            catalog_items.append({
                "序号": seq,
                "材料名称": name,
                "页码": page_range,
            })
            seq += 1

        return catalog_items

    @staticmethod
    def _calculate_material_page_count(
        contract: Any,
        archive_item_code: str,
        material_ids: list[int],
    ) -> int:
        """计算某检查项关联材料的总页数"""
        from apps.contracts.models.finalized_material import FinalizedMaterial

        if not material_ids:
            # 尝试通过 archive_item_code 查找
            materials = FinalizedMaterial.objects.filter(
                contract=contract,
                archive_item_code=archive_item_code,
            )
        else:
            materials = FinalizedMaterial.objects.filter(
                id__in=material_ids,
            )

        total_pages = 0
        for mat in materials:
            page_count = ArchivePlaceholderService._get_file_page_count(mat)
            if page_count > 0:
                total_pages += page_count
            else:
                total_pages += 1  # 无法识别页数的文件默认1页

        return total_pages

    @staticmethod
    def _get_file_page_count(material: Any) -> int:
        """读取归档材料文件的页数"""
        from pathlib import Path
        from django.conf import settings as django_settings

        file_path = Path(material.file_path)
        if not file_path.is_absolute():
            file_path = Path(django_settings.MEDIA_ROOT) / file_path

        if not file_path.exists():
            return 0

        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            try:
                from apps.documents.services.infrastructure.pdf_utils import get_pdf_page_count

                with open(str(file_path), "rb") as f:
                    return get_pdf_page_count(f, default=0)
            except Exception as e:
                logger.warning("读取PDF页数失败: %s, error: %s", material.original_filename, e)
                return 0
        elif suffix == ".docx":
            # docx 文件默认按1页计算（精确计算需要转PDF）
            return 1
        else:
            return 1
