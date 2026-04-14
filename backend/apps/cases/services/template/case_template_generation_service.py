"""
案件模板生成服务

使用 docxtpl 渲染模板并生成文档.

Requirements: 2.1, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 6.2, 6.3, 7.4
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from typing import Any, cast

from django.utils.translation import gettext_lazy as _
from docxtpl import DocxTemplate

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.utils.path import Path
from apps.documents.services.placeholders.fallback import build_docx_render_context

from .wiring import get_case_service, get_client_service, get_document_service

logger = logging.getLogger("apps.cases.services")


class CaseTemplateGenerationService:
    """案件模板生成服务"""

    LEGAL_REP_CERT_TEMPLATE = "法定代表人身份证明书"
    POWER_OF_ATTORNEY_TEMPLATE = "授权委托书"

    def generate_document(
        self,
        case_id: int,
        template_id: int,
        client_id: int | None = None,
        client_ids: list[int] | None = None,
        mode: str | None = None,
    ) -> tuple[bytes, str]:
        """
        生成模板文档

            case_id: 案件ID
            template_id: 模板ID
            client_id: 当事人ID(可选,用于法定代表人身份证明书、单独授权)
            client_ids: 当事人ID列表(可选,用于合并授权)
            mode: 授权模式(可选): 'individual' | 'combined'

            Tuple[bytes, str]: (文档字节流, 文件名)

            NotFoundError: 案件或模板不存在
            ValidationException: 模板文件无效或当事人无效

        Requirements: 2.1, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 6.2, 6.3, 7.4
        """
        case = self._get_case(case_id)
        template = self._get_template(template_id)
        template_path = self._get_template_path(template)
        client = None
        clients = None
        if self._is_legal_rep_cert_template(template):
            client = self._get_our_legal_client(case, client_id)
        elif self._is_power_of_attorney_template(template):
            if mode == "combined" and client_ids:
                clients = [self._get_our_client(case, cid) for cid in client_ids]
            elif client_id:
                client = self._get_our_client(case, client_id)
        context = self._build_context(case, client=client, clients=clients)
        content = self._render_template(template_path, context)
        case_name = getattr(case, "name", "") or "案件"
        template_name = template.name or "模板"
        client_name = client.name if client else None
        our_party_count = self._count_our_parties(case)
        is_combined = mode == "combined"
        filename = self._build_filename(
            template_name=template_name,
            case_name=case_name,
            client_name=client_name,
            is_combined=is_combined,
            our_party_count=our_party_count,
        )
        logger.info(
            "生成模板文档成功",
            extra={
                "case_id": case_id,
                "template_id": template_id,
                "client_id": client_id,
                "mode": mode,
                "output_filename": filename,
            },
        )
        return (content, filename)

    def _is_legal_rep_cert_template(self, template: Any) -> Any:
        """
        判断是否为法定代表人身份证明书模板

            template: DocumentTemplate 模型实例

            bool: 是否为法定代表人身份证明书模板
        """
        return template.name == self.LEGAL_REP_CERT_TEMPLATE

    def _is_power_of_attorney_template(self, template: Any) -> Any:
        """
        判断是否为授权委托书模板

            template: DocumentTemplate 模型实例

            bool: 是否为授权委托书模板
        """
        return template.name == self.POWER_OF_ATTORNEY_TEMPLATE

    def _get_our_client(self, case: Any, client_id: int) -> Any:
        """
        获取我方当事人

            case: Case 模型实例
            client_id: 当事人ID

            Client 模型实例

            ValidationException: 当事人不存在或非我方当事人

        Requirements: 4.3
        """
        client_service = get_client_service()
        client_dto = client_service.get_client_internal(client_id)
        if not client_dto:
            raise ValidationException(
                message=_("当事人不存在"),
                code="INVALID_CLIENT",
                errors={"client_id": f"ID 为 {client_id} 的当事人不存在"},
            )
        is_party = case.parties.filter(client_id=client_id, client__is_our_client=True).exists()
        if not is_party:
            raise ValidationException(
                message=_("当事人非我方当事人"),
                code="INVALID_OUR_CLIENT",
                errors={"client_id": f"ID 为 {client_id} 的当事人不是该案件的我方当事人"},
            )
        return client_dto

    def _get_our_legal_client(self, case: Any, client_id: int) -> Any:
        """
        获取我方法人当事人

            case: Case 模型实例
            client_id: 当事人ID

            Client 模型实例

            ValidationException: 当事人不存在、非我方当事人或非法人

        Requirements: 4.3
        """
        client = self._get_our_client(case, client_id)
        client_service = get_client_service()
        is_natural = client_service.is_natural_person_internal(client_id)
        if is_natural:
            raise ValidationException(
                message=_("当事人非法人"),
                code="INVALID_LEGAL_CLIENT",
                errors={"client_id": f"ID 为 {client_id} 的当事人不是法人"},
            )
        return client

    def _count_our_parties(self, case: Any) -> Any:
        """
        统计我方当事人数量

            case: Case 模型实例

            int: 我方当事人数量
        """
        return case.parties.filter(client__is_our_client=True).count()

    def _get_case(self, case_id: int) -> Any:
        """
        获取案件模型

            case_id: 案件ID

            Case 模型实例

            NotFoundError: 案件不存在
        """
        case_service = get_case_service()
        case = case_service.get_case_model_internal(case_id)
        if not case:
            raise NotFoundError(
                message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            )
        return case

    def _get_template(self, template_id: int) -> Any:
        """
        获取模板模型

            template_id: 模板ID

            DocumentTemplate 模型实例

            NotFoundError: 模板不存在
        """
        document_service = get_document_service()
        template = document_service.get_template_by_id_internal(template_id)
        if not template:
            raise NotFoundError(
                message=_("模板不存在"),
                code="TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            )
        return template

    def _get_template_path(self, template: Any) -> Path:
        """
        获取模板文件路径

            template: DocumentTemplate 模型实例

            模板文件路径

            ValidationException: 模板文件路径无效
        """
        location = (getattr(template, "file_path", None) or "").strip()
        if not location:
            raise ValidationException(
                message=_("模板文件路径为空"), code="TEMPLATE_FILE_EMPTY", errors={"template_id": str(template.id)}
            )
        path = Path(location)
        if not path.exists():
            raise ValidationException(
                message=_("模板文件不存在: %(path)s") % {"path": location},
                code="TEMPLATE_FILE_NOT_FOUND",
                errors={"template_path": location},
            )
        return path

    def _build_context(self, case: Any, client: Any | None = None, clients: Any | None = None) -> dict[str, Any]:
        """
        使用 EnhancedContextBuilder 构建上下文

            case: Case 模型实例
            client: 单个当事人(可选)
            clients: 当事人列表(可选,用于合并授权)

            占位符上下文字典

        Requirements: 3.1
        """
        from apps.cases.dependencies import get_enhanced_context_builder

        context_data: dict[str, Any] = {"case": case, "case_id": case.id}
        if client:
            context_data["client"] = client
        if clients:
            context_data["clients"] = clients
        return cast(dict[str, Any], get_enhanced_context_builder().build_context(context_data))

    def _render_template(self, template_path: Path, context: dict[str, Any]) -> bytes:
        """
        使用 docxtpl 渲染模板

            template_path: 模板文件路径
            context: 占位符上下文字典

            渲染后的文档字节流

            ValidationException: 模板渲染失败

        Requirements: 3.2, 3.3, 3.4
        """
        try:
            logger.info("渲染模板", extra={"template_path": str(template_path), "context_keys": list(context.keys())})
            doc = DocxTemplate(str(template_path))
            doc.render(build_docx_render_context(doc=doc, context=context))
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            return buffer.getvalue()
        except Exception as e:
            logger.error("模板渲染失败", exc_info=True, extra={"template_path": str(template_path), "error": str(e)})
            raise ValidationException(
                message=_("模板渲染失败: %(err)s") % {"err": str(e)},
                code="TEMPLATE_RENDER_ERROR",
                errors={"error": str(e)},
            ) from e

    def _build_filename(
        self,
        template_name: str,
        case_name: str,
        client_name: str | None = None,
        is_combined: bool = False,
        our_party_count: int = 1,
    ) -> str:
        """
        构建输出文件名

        文件名规则:
        - 普通模板: {模板名称}({案件名称})V1_{日期}.docx
        - 法定代表人身份证明书: {模板名称}({公司名称})V1_{日期}.docx
        - 授权委托书(单独授权,多当事人): {模板名称}({当事人名称})({案件名称})V1_{日期}.docx
        - 授权委托书(合并授权或单当事人): {模板名称}({案件名称})V1_{日期}.docx

            template_name: 模板名称
            case_name: 案件名称
            client_name: 当事人名称(可选)
            is_combined: 是否为合并授权
            our_party_count: 我方当事人数量

            安全的文件名

        Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
        """
        date_str = datetime.now().strftime("%Y%m%d")
        safe_template_name = self._safe_name(template_name)
        safe_case_name = self._safe_name(case_name)
        if template_name == self.LEGAL_REP_CERT_TEMPLATE and client_name:
            safe_client_name = self._safe_name(client_name)
            return f"{safe_template_name}({safe_client_name})V1_{date_str}.docx"
        if template_name == self.POWER_OF_ATTORNEY_TEMPLATE:
            if not is_combined and our_party_count > 1 and client_name:
                safe_client_name = self._safe_name(client_name)
                return f"{safe_template_name}({safe_client_name})({safe_case_name})V1_{date_str}.docx"
            return f"{safe_template_name}({safe_case_name})V1_{date_str}.docx"
        return f"{safe_template_name}({safe_case_name})V1_{date_str}.docx"

    def _safe_name(self, name: str) -> str:
        """
        将名称转换为安全的文件名部分

        替换特殊字符: /, \\, \\n, \\r, \\t

            name: 原始名称

            安全的名称

        Requirements: 4.2
        """
        value = (name or "").strip()
        value = value.replace("/", "／").replace("\\", "＼")
        value = value.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        value = re.sub("\\s+", " ", value).strip()
        return value or "未命名"
