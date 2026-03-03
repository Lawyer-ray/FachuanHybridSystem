"""
统一模板生成服务

整合 CaseTemplateGenerationService 和 AuthorizationMaterialGenerationService 的功能,
提供统一的模板生成入口,支持通过 template_id 或 function_code 查找模板.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.6
"""

from __future__ import annotations

import logging
from typing import Any, cast

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, ValidationException

from .wiring import get_case_service

logger = logging.getLogger("apps.cases.services")


class UnifiedTemplateGenerationService:
    """
    统一模板生成服务

    提供统一的 generate_document 方法,支持:
    - 通过 template_id 直接指定模板
    - 通过 function_code 查找模板
    - 特殊模板的当事人验证和处理

    Requirements: 1.1, 1.2, 1.3, 1.4, 1.6
    """

    # 特殊模板的 function_code 常量
    LEGAL_REP_CERT_CODE = "legal_rep_certificate"
    POWER_OF_ATTORNEY_CODE = "power_of_attorney"
    AUTHORITY_LETTER_CODE = "authority_letter"

    def __init__(
        self,
        template_lookup_service: Any | None = None,
        resolver: Any | None = None,
        party_selection_policy: Any | None = None,
        context_builder: Any | None = None,
        renderer: Any | None = None,
        filename_policy: Any | None = None,
        party_repo: Any | None = None,
    ) -> None:
        from .unified import (
            CasePartyRepository,
            DocxRenderer,
            FilenamePolicy,
            PartySelectionPolicy,
            TemplateContextBuilder,
            TemplateResolver,
        )

        self._party_repo = party_repo or CasePartyRepository()
        self._resolver = resolver or template_lookup_service or TemplateResolver()
        self._party_selection_policy = party_selection_policy or PartySelectionPolicy(repo=self._party_repo)
        self._context_builder = context_builder or TemplateContextBuilder()
        self._renderer = renderer or DocxRenderer()
        self._filename_policy = filename_policy or FilenamePolicy()

    def generate_document(
        self,
        case_id: int,
        template_id: int | None = None,
        function_code: str | None = None,
        client_id: int | None = None,
        client_ids: list[int] | None = None,
        mode: str | None = None,
    ) -> tuple[bytes, str]:
        """
        统一生成模板文档

            case_id: 案件ID
            template_id: 模板ID(可选,优先使用)
            function_code: 功能标识(可选,当 template_id 为空时使用)
            client_id: 当事人ID(可选,用于特殊模板)
            client_ids: 当事人ID列表(可选,用于合并授权)
            mode: 授权模式(可选): 'individual' | 'combined'

            Tuple[bytes, str]: (文档字节流, 文件名)

            NotFoundError: 案件或模板不存在
            ValidationException: 参数无效或模板渲染失败

        Requirements: 1.1, 1.2, 1.3, 1.4, 1.6
        """
        # 验证参数:必须提供 template_id 或 function_code
        if template_id is None and not function_code:
            raise ValidationException(
                message=_("必须提供 template_id 或 function_code"),
                code="INVALID_PARAMS",
                errors={"params": str(_("必须提供 template_id 或 function_code"))},
            )

        # 获取案件
        case = self._get_case(case_id)

        resolved = self._resolver.resolve(template_id=template_id, function_code=function_code)
        selected = self._party_selection_policy.select(
            case=case,
            function_code=resolved.effective_function_code,
            client_id=client_id,
            client_ids=client_ids,
            mode=mode,
            legal_rep_cert_code=self.LEGAL_REP_CERT_CODE,
            power_of_attorney_code=self.POWER_OF_ATTORNEY_CODE,
        )
        context = self._context_builder.build(case=case, client=selected.client, clients=selected.clients)
        content = self._renderer.render(template_path=resolved.template_path, context=context)

        from .unified import FilenameInputs

        filename = self._filename_policy.build(
            inputs=FilenameInputs(
                template_name=resolved.template.name or "模板",
                case_name=getattr(case, "name", "") or "案件",
                client_name=(selected.client.name if selected.client else None),
                function_code=resolved.effective_function_code,
                mode=mode,
                our_party_count=self._party_repo.count_our_parties(case),
            ),
            legal_rep_cert_code=self.LEGAL_REP_CERT_CODE,
            power_of_attorney_code=self.POWER_OF_ATTORNEY_CODE,
        )

        logger.info(
            "统一模板生成成功",
            extra={
                "case_id": case_id,
                "template_id": cast(int, resolved.template.id) if resolved.template else None,
                "function_code": resolved.effective_function_code,
                "client_id": client_id,
                "mode": mode,
                "output_filename": filename,
            },
        )

        return content, filename

    def get_template_info(self, template_id: int | None = None, function_code: str | None = None) -> dict[str, Any]:
        """
        获取模板信息(包含 function_code)

            template_id: 模板ID
            function_code: 功能标识

            模板信息字典,包含 id, name, function_code 等

            NotFoundError: 模板不存在
            ValidationException: 参数无效
        """
        if template_id is None and not function_code:
            raise ValidationException(
                message=_("必须提供 template_id 或 function_code"),
                code="INVALID_PARAMS",
                errors={"params": str(_("必须提供 template_id 或 function_code"))},
            )

        return self._resolver.get_template_info(template_id=template_id, function_code=function_code)

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
