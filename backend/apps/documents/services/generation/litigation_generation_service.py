"""
诉讼文书生成服务

使用统一 LLM 服务生成诉讼文书(起诉状、答辩状).

主要改进(2026-01):
- 统一结构化输出解析
- 直接返回 Pydantic 对象
- 自动进行 schema 校验

Requirements: 3.1, 3.2, 3.3
"""

import logging
from datetime import date
from typing import Any, cast

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.interfaces import ServiceLocator
from apps.core.utils.path import Path
from apps.documents.storage import get_docx_templates_root

from .litigation_context_builder import LitigationContextBuilder
from .litigation_llm_generator import LitigationLLMGenerator
from .outputs import ComplaintOutput, DefenseOutput

logger = logging.getLogger("apps.documents.generation")


class LitigationGenerationService:
    """
    诉讼文书生成服务

    使用提示词 + LLM + 结构化解析的生成链.

    遵循四层架构规范:
    - 依赖注入构造函数
    - 延迟加载依赖
    - 业务逻辑封装
    """

    # 模板路径配置
    TEMPLATE_DIR = get_docx_templates_root() / "2-案件材料"
    COMPLAINT_TEMPLATE = TEMPLATE_DIR / "1-起诉材料" / "1-起诉状和反诉答辩状" / "1-起诉状.docx"
    DEFENSE_TEMPLATE = TEMPLATE_DIR / "2-答辩材料" / "1-答辩状和反诉状" / "1-答辩状.docx"

    def __init__(
        self,
        llm_generator: LitigationLLMGenerator | None = None,
        context_builder: LitigationContextBuilder | None = None,
    ) -> None:
        """
        初始化服务(依赖注入)

        Args:
            llm_client: LLM 客户端实例(可选,延迟加载)
        """
        self._llm_generator = llm_generator
        self._context_builder = context_builder

    @property
    def llm_generator(self) -> LitigationLLMGenerator:
        if self._llm_generator is None:
            self._llm_generator = LitigationLLMGenerator()
        return self._llm_generator

    @property
    def context_builder(self) -> LitigationContextBuilder:
        if self._context_builder is None:
            self._context_builder = LitigationContextBuilder()
        return self._context_builder

    def generate_complaint(self, case_data: dict[str, Any]) -> Any:
        """
        生成起诉状

        使用统一 LLM 结构化输出流程直接获取结构化结果.

        Args:
            case_data: 案件数据字典,包含以下字段:
                - cause_of_action: 案由
                - plaintiff: 原告
                - defendant: 被告
                - litigation_request: 诉讼请求
                - facts_and_reasons: 事实与理由

        Returns:
            ComplaintOutput: 起诉状输出结构

        Raises:
            ValidationException: 生成失败或数据验证失败

        Requirements: 3.1, 3.2, 3.3
        """
        return self.llm_generator.generate_complaint(case_data)

    def generate_defense(self, case_data: dict[str, Any]) -> Any:
        """
        生成答辩状

        使用统一 LLM 结构化输出流程直接获取结构化结果.

        Args:
            case_data: 案件数据字典,包含以下字段:
                - cause_of_action: 案由
                - plaintiff: 原告
                - defendant: 被告
                - defense_opinion: 答辩意见
                - defense_reasons: 答辩理由

        Returns:
            DefenseOutput: 答辩状输出结构

        Raises:
            ValidationException: 生成失败或数据验证失败

        Requirements: 3.1, 3.2, 3.3
        """
        return self.llm_generator.generate_defense(case_data)

    def generate_complaint_document(self, case_id: int, skip_llm: bool = True) -> tuple[str, bytes]:
        """
        生成起诉状文档(返回文件名和字节流)

        Args:
            case_id: 案件 ID
            skip_llm: 是否跳过 LLM 生成(默认 True,用于测试占位符)

        Returns:
            tuple[str, bytes]: (文件名, 文档字节流)

        Raises:
            NotFoundError: 案件不存在
            ValidationException: 生成失败
        """
        # 1. 获取案件数据

        case_service = ServiceLocator.get_case_service()
        case_dto = case_service.get_case_by_id_internal(case_id)

        if not case_dto:
            raise NotFoundError(message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": case_id})

        # 2. 提取案件信息
        case_data = self.context_builder.extract_complaint_prompt_data(case_dto)

        # 3. 使用 LLM 生成内容或使用模拟数据
        if skip_llm:
            logger.info("跳过 LLM 生成,使用模拟数据测试占位符")
            llm_result = self._get_mock_complaint_output(case_data)
        else:
            llm_result = self.generate_complaint(case_data)

        # 4. 准备模板上下文
        context = self.context_builder.build_complaint_context(case_dto=case_dto, llm_result=llm_result)

        # 5. 生成文件名
        filename = self._generate_filename(case_id, "complaint")
        logger.info("生成起诉状文件名: %s", filename)

        # 6. 渲染模板
        doc_bytes = self._render_template(self.COMPLAINT_TEMPLATE, context)

        return filename, doc_bytes

    def generate_defense_document(self, case_id: int, skip_llm: bool = True) -> tuple[str, bytes]:
        """
        生成答辩状文档(返回文件名和字节流)

        Args:
            case_id: 案件 ID
            skip_llm: 是否跳过 LLM 生成(默认 True,用于测试占位符)

        Returns:
            tuple[str, bytes]: (文件名, 文档字节流)

        Raises:
            NotFoundError: 案件不存在
            ValidationException: 生成失败
        """
        # 1. 获取案件数据

        case_service = ServiceLocator.get_case_service()
        case_dto = case_service.get_case_by_id_internal(case_id)

        if not case_dto:
            raise NotFoundError(message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": case_id})

        # 2. 提取案件信息
        case_data = self.context_builder.extract_defense_prompt_data(case_dto)

        # 3. 使用 LLM 生成内容或使用模拟数据
        if skip_llm:
            logger.info("跳过 LLM 生成,使用模拟数据测试占位符")
            llm_result = self._get_mock_defense_output(case_data)
        else:
            llm_result = self.generate_defense(case_data)

        # 4. 准备模板上下文
        context = self.context_builder.build_defense_context(case_dto=case_dto, llm_result=llm_result)

        # 5. 生成文件名
        filename = self._generate_filename(case_id, "defense")
        logger.info("生成答辩状文件名: %s", filename)

        # 6. 渲染模板
        doc_bytes = self._render_template(self.DEFENSE_TEMPLATE, context)

        return filename, doc_bytes

    def get_preview_context(self, case_id: int, litigation_type: str) -> dict[str, str]:
        case_service = ServiceLocator.get_case_service()
        case_dto = case_service.get_case_by_id_internal(case_id)
        if not case_dto:
            raise NotFoundError(message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": case_id})

        if litigation_type == "complaint":
            template_path = self.COMPLAINT_TEMPLATE
            case_data = self.context_builder.extract_complaint_prompt_data(case_dto)
            llm_result = self._get_mock_complaint_output(case_data)
            context = self.context_builder.build_complaint_context(case_dto=case_dto, llm_result=llm_result)
        elif litigation_type == "defense":
            template_path = self.DEFENSE_TEMPLATE
            case_data = self.context_builder.extract_defense_prompt_data(case_dto)
            llm_result = self._get_mock_defense_output(case_data)
            context = self.context_builder.build_defense_context(case_dto=case_dto, llm_result=llm_result)
        else:
            raise ValidationException(
                message=_("不支持的诉讼类型: %(t)s") % {"t": litigation_type},
                code="INVALID_LITIGATION_TYPE",
            )

        from .pipeline import DocxPreviewService

        preview_result = DocxPreviewService().preview(template_path, context)
        return cast(dict[str, str], preview_result)

    def _generate_filename(self, case_id: int, doc_type: str) -> str:
        """
        生成文件名

        Args:
            case_id: 案件 ID
            doc_type: 文档类型 ('complaint' 或 'defense')

        Returns:
            str: 生成的文件名

        Requirements: 10.5
        """
        from apps.documents.services.placeholders.litigation import FilenameService

        filename_service = FilenameService()

        if doc_type == "complaint":
            return str(filename_service.generate_complaint_filename(case_id))
        if doc_type == "defense":
            return str(filename_service.generate_defense_filename(case_id))
        raise ValidationException(
                message=_("不支持的文档类型: %(t)s") % {"t": doc_type},
                code="INVALID_DOC_TYPE",
                errors={"doc_type": doc_type},
            )

    def _get_mock_complaint_output(self, case_data: dict[str, Any]) -> ComplaintOutput:
        """
        获取模拟的起诉状输出(用于测试占位符)

        Args:
            case_data: 案件数据

        Returns:
            模拟的 ComplaintOutput
        """
        from .outputs import PartyInfo

        return ComplaintOutput(
            title=f"{case_data.get('cause_of_action', '民事纠纷')}起诉状",
            parties=[
                PartyInfo(
                    name=case_data.get("plaintiff", "原告姓名"),
                    role="原告",
                    id_number="110101199001011234",
                    address="北京市朝阳区测试路1号",
                ),
                PartyInfo(
                    name=case_data.get("defendant", "被告姓名"),
                    role="被告",
                    id_number="110101199002021234",
                    address="北京市海淀区测试路2号",
                ),
            ],
            litigation_request="一、请求判令被告支付原告欠款人民币100,000元;\n二、请求判令被告承担本案诉讼费用.",
            facts_and_reasons=(
                "原告与被告于2023年1月1日签订借款合同,"
                "约定被告向原告借款人民币100,000元,"
                "借款期限为一年,到期后被告应当归还本金及利息.\n"
                "借款到期后,原告多次催告被告还款,"
                "但被告一直拖延不还.\n"
                "综上所述,被告的行为已经严重侵害了原告的合法权益,"
                "为维护原告的合法权益,"
                "特向贵院提起诉讼,请求依法判决."
            ),
            evidence=["借款合同", "转账记录", "催款记录"],
        )

    def _get_mock_defense_output(self, case_data: dict[str, Any]) -> DefenseOutput:
        """
        获取模拟的答辩状输出(用于测试占位符)

        Args:
            case_data: 案件数据

        Returns:
            模拟的 DefenseOutput
        """
        from .outputs import PartyInfo

        return DefenseOutput(
            title=f"{case_data.get('cause_of_action', '民事纠纷')}答辩状",
            parties=[
                PartyInfo(
                    name=case_data.get("plaintiff", "原告姓名"),
                    role="原告",
                    id_number="110101199001011234",
                    address="北京市朝阳区测试路1号",
                ),
                PartyInfo(
                    name=case_data.get("defendant", "被告姓名"),
                    role="被告",
                    id_number="110101199002021234",
                    address="北京市海淀区测试路2号",
                ),
            ],
            defense_opinion="答辩人不同意原告的全部诉讼请求",
            defense_reasons=(
                "一、原告所述借款事实不存在,"
                "答辩人从未向原告借款.\n"
                "二、原告提供的所谓借款合同系伪造,"
                "答辩人从未在该合同上签字.\n"
                "三、原告提供的转账记录与本案无关,"
                "该笔款项系其他经济往来.\n"
                "综上所述,原告的诉讼请求缺乏事实和法律依据,"
                "请求贵院依法驳回原告的全部诉讼请求."
            ),
            evidence=["银行流水", "聊天记录", "证人证言"],
        )

    def _render_template(self, template_path: Path, context: dict[str, Any]) -> bytes:
        """渲染 docx 模板"""
        if not template_path.exists():
            raise ValidationException(
                message=_("模板文件不存在: %(p)s") % {"p": template_path},
                code="TEMPLATE_NOT_FOUND",
                errors={"template_path": str(template_path)},
            )

        try:
            # 记录上下文键用于调试
            logger.info("模板上下文包含的占位符: %s", list(context.keys()))
            if "年份" not in context:
                context["年份"] = str(date.today().year)

            from .pipeline import DocxRenderer

            rendered_content = DocxRenderer().render(str(template_path), context)
            return cast(bytes, rendered_content)

        except Exception as e:
            logger.error("模板渲染失败: %s", e, exc_info=True)
            raise ValidationException(
                message=_("模板渲染失败: %(e)s") % {"e": e}, code="TEMPLATE_RENDER_ERROR", errors={"error": str(e)}
            ) from e
