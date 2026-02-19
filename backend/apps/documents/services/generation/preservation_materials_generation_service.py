"""
财产保全材料生成服务

生成财产保全申请书、暂缓送达申请书和全套财产保全材料.

Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
"""

import io
import logging
import zipfile
from datetime import datetime
from typing import Any, cast

from docxtpl import DocxTemplate

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.path import Path
from apps.documents.services.placeholders import EnhancedContextBuilder
from apps.documents.services.wiring import get_case_service, get_document_service

logger = logging.getLogger("apps.documents.generation")
FUNCTION_CODE_PRESERVATION_APPLICATION = "preservation_application"
FUNCTION_CODE_DELAY_DELIVERY_APPLICATION = "delay_delivery_application"


class PreservationMaterialsGenerationService:
    """财产保全材料生成服务"""

    def __init__(
        self,
        party_service: Any | None = None,
        signature_service: Any | None = None,
        property_clue_service: Any | None = None,
        template_service: Any | None = None,
    ) -> None:
        """
        依赖注入构造函数

        Args:
            party_service: 当事人信息服务(可选)
            signature_service: 签名信息服务(可选)
            property_clue_service: 财产线索服务(可选)
            template_service: 模板服务(可选)
        """
        self._party_service = party_service
        self._signature_service = signature_service
        self._property_clue_service = property_clue_service
        self._template_service = template_service

    @property
    def party_service(self) -> Any:
        if self._party_service is None:
            from apps.documents.services.placeholders.litigation import PreservationPartyService

            self._party_service = PreservationPartyService()
        return self._party_service

    @property
    def signature_service(self) -> Any:
        if self._signature_service is None:
            from apps.documents.services.placeholders.litigation import PreservationSignatureService

            self._signature_service = PreservationSignatureService()
        return self._signature_service

    @property
    def property_clue_service(self) -> Any:
        if self._property_clue_service is None:
            from apps.documents.services.placeholders.litigation import PreservationPropertyClueService

            self._property_clue_service = PreservationPropertyClueService()
        return self._property_clue_service

    def generate_preservation_application(self, case_id: int) -> tuple[bytes, str]:
        """
        生成财产保全申请书

        Args:
            case_id: 案件ID

        Returns:
            Tuple[bytes, str]: (文档字节流, 文件名)

        Raises:
            NotFoundError: 案件或模板不存在
            ValidationException: 模板渲染失败

        Requirements: 2.1, 3.1, 3.4
        """
        case = self._get_case(case_id)
        template_path = self._get_template_path_by_function_code(case_id, FUNCTION_CODE_PRESERVATION_APPLICATION)
        if not template_path:
            raise NotFoundError(
                message="未找到财产保全申请书模板",
                code="TEMPLATE_NOT_FOUND",
                errors={"function_code": FUNCTION_CODE_PRESERVATION_APPLICATION},
            )
        context = self._build_context(case=case)
        content = self._render_template(template_path, context)
        filename = self._build_filename("财产保全申请书", case)
        return (content, filename)

    def generate_delay_delivery_application(self, case_id: int) -> tuple[bytes, str]:
        """
        生成暂缓送达申请书

        Args:
            case_id: 案件ID

        Returns:
            Tuple[bytes, str]: (文档字节流, 文件名)

        Requirements: 2.2, 3.2, 3.4
        """
        case = self._get_case(case_id)
        template_path = self._get_template_path_by_function_code(case_id, FUNCTION_CODE_DELAY_DELIVERY_APPLICATION)
        if not template_path:
            raise NotFoundError(
                message="未找到暂缓送达申请书模板",
                code="TEMPLATE_NOT_FOUND",
                errors={"function_code": FUNCTION_CODE_DELAY_DELIVERY_APPLICATION},
            )
        context = self._build_context(case=case)
        content = self._render_template(template_path, context)
        filename = self._build_filename("暂缓送达申请书", case)
        return (content, filename)

    def generate_full_package(self, case_id: int) -> tuple[bytes, str]:
        """
        生成全套财产保全材料 zip 包

        Args:
            case_id: 案件ID

        Returns:
            Tuple[bytes, str]: (zip字节流, 文件名)

        Requirements: 3.3, 3.4, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
        """
        case = self._get_case(case_id)
        respondents = self._get_respondents(case_id)
        if not respondents:
            raise ValidationException(
                message="案件没有被申请人,无法生成财产保全材料", code="NO_RESPONDENTS", errors={"case_id": str(case_id)}
            )
        missing_clue_respondents = self.property_clue_service.get_respondents_without_clues(case_id)
        now = datetime.now()
        case_name = getattr(case, "name", "") or "案件"
        zip_filename = f"全套保全材料({case_name})V1_{now.strftime('%Y%m%d')}.zip"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            try:
                preservation_bytes, _ = self.generate_preservation_application(case_id)
                zf.writestr("财产保全申请书.docx", preservation_bytes)
            except NotFoundError:
                logger.warning(f"未找到财产保全申请书模板: case_id={case_id}")
            try:
                delay_bytes, _ = self.generate_delay_delivery_application(case_id)
                zf.writestr("暂缓送达申请书.docx", delay_bytes)
            except NotFoundError:
                logger.warning(f"未找到暂缓送达申请书模板: case_id={case_id}")
            zf.writestr("保单保函/", "")
            if missing_clue_respondents:
                report = self._generate_missing_clues_report(missing_clue_respondents)
                zf.writestr("当前保全手续所缺材料.md", report)
        buffer.seek(0)
        return (buffer.getvalue(), zip_filename)

    def get_missing_clues_report(self, case_id: int) -> str | None | None:
        """
        生成缺失财产线索报告

        Args:
            case_id: 案件ID

        Returns:
            Optional[str]: 报告内容,如果所有被申请人都有财产线索则返回 None
        """
        missing_clue_respondents = self.property_clue_service.get_respondents_without_clues(case_id)
        if not missing_clue_respondents:
            return None
        return self._generate_missing_clues_report(missing_clue_respondents)

    def _generate_missing_clues_report(self, missing_respondents: list[str]) -> str:
        """
        生成缺失材料报告内容

        Args:
            missing_respondents: 缺失财产线索的被申请人名称列表

        Returns:
            str: 报告内容

        Requirements: 10.5, 10.6
        """
        lines = ["# 当前保全手续所缺材料", "", "以下被申请人暂无财产线索,请补充:", ""]
        for index, name in enumerate(missing_respondents, 1):
            lines.append(f"{index}. {name}")
        return "\n".join(lines)

    def _get_case(self, case_id: int) -> Any:
        """获取案件"""
        case_service = get_case_service()
        case = case_service.get_case_model_internal(case_id)
        if not case:
            raise NotFoundError(message="案件不存在", code="CASE_NOT_FOUND", errors={"case_id": str(case_id)})
        return case

    def _get_respondents(self, case_id: int) -> list[Any]:
        """
        获取被申请人(被告)列表

        Args:
            case_id: 案件ID

        Returns:
            List: 被申请人 DTO 列表
        """
        from apps.core.enums import LegalStatus

        case_service = get_case_service()
        return cast(list[Any], case_service.get_case_parties_internal(case_id, legal_status=LegalStatus.DEFENDANT))

    def _get_template_path_by_function_code(self, case_id: int, function_code: str) -> Path | None:
        """
        从案件绑定的模板或通用模板中查找指定功能代码的模板路径

        查找顺序:
        1. 先从案件绑定记录中查找(通过 function_code 或模板名称)
        2. 如果未找到,从通用模板中查找

        Args:
            case_id: 案件ID
            function_code: 模板功能代码

        Returns:
            模板文件路径,如果未找到则返回 None
        """
        from django.db.models import Q

        from apps.documents.models import DocumentTemplate

        name_keywords = {"preservation_application": "财产保全申请书", "delay_delivery_application": "暂缓送达申请书"}
        name_keyword = name_keywords.get(function_code, "")
        case_service = get_case_service()
        if name_keyword:
            bindings = case_service.get_case_template_bindings_by_name_internal(case_id, name_keyword)
            if bindings:
                binding = bindings[0]
                document_service = get_document_service()
                template_dto = document_service.get_template_by_id_internal(binding.template_id)
                if template_dto and template_dto.file_path:
                    return Path(template_dto.file_path)
        template_query = Q(is_active=True, template_type="case")
        if name_keyword:
            template_query &= Q(function_code=function_code) | Q(name__contains=name_keyword)
        else:
            template_query &= Q(function_code=function_code)
        template = DocumentTemplate.objects.filter(template_query).first()
        if template:
            location = template.get_file_location()
            if location:
                return Path(location)
        return None

    def has_template(self, case_id: int, function_code: str) -> bool:
        """
        检查案件是否绑定了指定功能代码的模板

        Args:
            case_id: 案件ID
            function_code: 模板功能代码

        Returns:
            是否存在该模板
        """
        template_path = self._get_template_path_by_function_code(case_id, function_code)
        return template_path is not None

    def _build_context(self, *, case: Any) -> dict[str, Any]:
        """构建模板上下文"""
        context_data: dict[str, Any] = {"case": case}
        return EnhancedContextBuilder().build_context(context_data)

    def _render_template(self, template_path: Path, context: dict[str, Any]) -> bytes:
        """渲染模板"""
        if not template_path.exists():
            raise ValidationException(
                message=f"模板文件不存在: {template_path}",
                code="TEMPLATE_NOT_FOUND",
                errors={"template_path": str(template_path)},
            )
        try:
            logger.info(
                "财产保全材料渲染模板", extra={"template_path": str(template_path), "keys": list[Any](context.keys())}
            )
            doc = DocxTemplate(str(template_path))
            doc.render(context)
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            return buffer.getvalue()
        except Exception as e:
            logger.error("模板渲染失败", exc_info=True, extra={"template_path": str(template_path), "error": str(e)})
            raise ValidationException(
                message=f"模板渲染失败: {e!s}", code="TEMPLATE_RENDER_ERROR", errors={"error": str(e)}
            ) from e

    def _build_filename(self, template_name: str, case: Any) -> str:
        """
        构建文件名

        格式: {模板名称}({案件名称})V1_{日期}.docx

        Args:
            template_name: 模板名称
            case: 案件对象

        Returns:
            str: 文件名

        Requirements: 3.1, 3.2, 3.4
        """
        date_str = datetime.now().strftime("%Y%m%d")
        case_name = getattr(case, "name", "") or "案件"
        return f"{template_name}({case_name})V1_{date_str}.docx"
