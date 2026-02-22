"""Business logic services."""

from django.utils.translation import gettext_lazy as _
import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path as StdPath
from typing import Any, ClassVar, cast

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.path import Path
from apps.documents.models import DocumentTemplate, DocumentTemplateType
from apps.documents.services.generation.path_utils import resolve_media_path, safe_arcname, safe_name
from apps.documents.services.placeholders import EnhancedContextBuilder

logger = logging.getLogger("apps.documents.generation")


# 模板名称常量(用于从案件绑定模板中匹配)
TEMPLATE_NAME_AUTHORITY_LETTER = "所函"
TEMPLATE_NAME_LEGAL_REP_CERT = "法定代表人身份证明书"
TEMPLATE_NAME_POWER_OF_ATTORNEY = "授权委托书"


class AuthorizationMaterialGenerationService:
    # 保留硬编码路径作为后备方案
    TEMPLATE_DIR = (
        Path(__file__).parent.parent.parent / "docx_templates" / "2-案件材料" / "4-通用材料" / "1-授权委托材料"
    )
    AUTHORITY_LETTER_TEMPLATE = TEMPLATE_DIR / "所函.docx"
    LEGAL_REP_CERT_TEMPLATE = TEMPLATE_DIR / "法定代表人身份证明书.docx"

    def __init__(
        self, *, case_service: Any | None = None, client_service: Any | None = None, document_service: Any | None = None
    ) -> None:
        self._case_service = case_service
        self._client_service = client_service
        self._document_service = document_service

    @property
    def case_service(self) -> Any:
        if self._case_service is None:
            raise RuntimeError("AuthorizationMaterialGenerationService.case_service 未注入")
        return self._case_service

    @property
    def client_service(self) -> Any:
        if self._client_service is None:
            raise RuntimeError("AuthorizationMaterialGenerationService.client_service 未注入")
        return self._client_service

    @property
    def document_service(self) -> Any:
        if self._document_service is None:
            raise RuntimeError("AuthorizationMaterialGenerationService.document_service 未注入")
        return self._document_service

    def generate_authority_letter_document(self, case_id: int) -> tuple[bytes, str]:
        case = self._get_case(case_id)
        context = self._build_context(case=case)

        # 优先从案件绑定模板中查找
        template_path = self._get_template_path_from_case_bindings(case_id, TEMPLATE_NAME_AUTHORITY_LETTER)
        if not template_path:
            # 后备:使用硬编码路径
            template_path = self.AUTHORITY_LETTER_TEMPLATE

        content = self._render_template(template_path, context) # type: ignore[no-any-return]
        filename = self._build_authority_letter_filename(case_name=getattr(case, "name", "") or "")
        return content, filename

    def generate_legal_rep_certificate_document(self, case_id: int, client_id: int) -> tuple[bytes, str]:
        case = self._get_case(case_id)
        client = self._get_our_legal_client(case, client_id)
        context = self._build_context(case=case, client=client)

        # 优先从案件绑定模板中查找
        template_path = self._get_template_path_from_case_bindings(case_id, TEMPLATE_NAME_LEGAL_REP_CERT)
        if not template_path:
            # 后备:使用硬编码路径
            template_path = self.LEGAL_REP_CERT_TEMPLATE

        content = self._render_template(template_path, context) # type: ignore[no-any-return]
        filename = self._build_legal_rep_certificate_filename(company_name=getattr(client, "name", "") or "")
        return content, filename

    def generate_power_of_attorney_document(self, case_id: int, client_id: int) -> tuple[bytes, str]:
        case = self._get_case(case_id)
        client = self._get_our_client(case, client_id)

        # 优先从案件绑定模板中查找
        template_path = self._get_template_path_from_case_bindings(case_id, TEMPLATE_NAME_POWER_OF_ATTORNEY)
        if template_path:
            # 使用案件绑定的模板
            pass
        else:
            # 后备:从数据库查找
            template = self._get_power_of_attorney_template_from_db()
            template_path = self._get_template_path(template)

        context = self._build_power_of_attorney_context(case=case, selected_clients=[client])
        self._validate_power_of_attorney_context(context)

        content = self._render_template(template_path, context)
        filename = self._build_power_of_attorney_filename(case=case, selected_clients=[client])
        return content, filename

    def generate_power_of_attorney_combined_document(self, case_id: int, client_ids: list[int]) -> tuple[bytes, str]:
        case = self._get_case(case_id)

        selected_clients: list[Any] = []
        for client_id in client_ids:
            selected_clients.append(self._get_our_client(case, client_id))

        # 优先从案件绑定模板中查找
        template_path = self._get_template_path_from_case_bindings(case_id, TEMPLATE_NAME_POWER_OF_ATTORNEY)
        if template_path:
            # 使用案件绑定的模板
            pass
        else:
            # 后备:从数据库查找
            template = self._get_power_of_attorney_template_from_db()
            template_path = self._get_template_path(template)

        context = self._build_power_of_attorney_context(case=case, selected_clients=selected_clients)
        self._validate_power_of_attorney_context(context)

        content = self._render_template(template_path, context)
        filename = self._build_power_of_attorney_filename(case=case, selected_clients=selected_clients, combined=True)
        return content, filename

    def generate_full_authorization_package(self, case_id: int) -> tuple[bytes, str]:
        from apps.core.config import get_config

        case = self._get_case(case_id)

        our_parties = self._get_our_parties(case)
        if not our_parties:
            raise ValidationException(
                message=_("没有我方当事人,无法生成全套授权委托材料"),
                code="NO_OUR_PARTIES",
                errors={"case_id": str(case_id)},
            )

        missing_lines: list[str] = []

        now = datetime.now()
        zip_filename = f"全套授权委托材料({getattr(case, 'name', '') or '案件'})V1_{now.strftime('%Y%m%d')}.zip"

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            self._zip_add_generated_docs(zf, case=case, our_parties=our_parties)
            media_root = get_config("django.media_root", None)
            if not media_root:
                raise RuntimeError("django.media_root 未配置")
            self._zip_add_client_identity_docs(
                zf, our_parties=our_parties, media_root=str(media_root), missing_lines=missing_lines
            )
            self._zip_add_lawyer_licenses(zf, case=case, missing_lines=missing_lines)
            if missing_lines:
                self._zip_add_missing_markdown(zf, missing_lines=missing_lines)

        buffer.seek(0)
        return buffer.getvalue(), zip_filename

    def _get_our_parties(self, case: Any) -> list[Any]:
        try:
            parties = list(case.parties.select_related("client").all())
        except Exception as e:
            logger.warning("获取案件当事人失败", extra={"case_id": getattr(case, "id", None), "error": str(e)})
            parties: list[Any] = []
        return [p for p in parties if getattr(getattr(p, "client", None), "is_our_client", False)]

    def _zip_add_generated_docs(self, zf: zipfile.ZipFile, *, case: Any, our_parties: list[Any]) -> None:
        case_id = getattr(case, "id", None)
        if not case_id:
            raise ValidationException(message=_("案件 ID 无效"), code="INVALID_CASE_ID", errors={})

        # 检查案件绑定的模板中是否有所函
        has_authority_letter = self._has_template_in_case_bindings(int(case_id), TEMPLATE_NAME_AUTHORITY_LETTER)
        if has_authority_letter:
            authority_bytes, authority_filename = self.generate_authority_letter_document(int(case_id))
            zf.writestr(self._safe_arcname(f"所函/{authority_filename}"), authority_bytes)

        # 检查案件绑定的模板中是否有授权委托书
        has_power_of_attorney = self._has_template_in_case_bindings(int(case_id), TEMPLATE_NAME_POWER_OF_ATTORNEY)
        if has_power_of_attorney:
            client_ids = [int(p.client_id) for p in our_parties if getattr(p, "client_id", None)]
            poa_bytes, poa_filename = self.generate_power_of_attorney_combined_document(int(case_id), client_ids)
            zf.writestr(self._safe_arcname(f"授权委托书/{poa_filename}"), poa_bytes)

        # 检查案件绑定的模板中是否有法定代表人身份证明书
        has_legal_rep_cert = self._has_template_in_case_bindings(int(case_id), TEMPLATE_NAME_LEGAL_REP_CERT)
        if has_legal_rep_cert:
            legal_parties = [
                p
                for p in our_parties
                if getattr(getattr(p, "client", None), "client_type", "") in {"legal", "non_legal_org"}
            ]
            for party in legal_parties:
                client_id = getattr(party, "client_id", None)
                if not client_id:
                    continue
                content, filename = self.generate_legal_rep_certificate_document(int(case_id), int(client_id))
                zf.writestr(self._safe_arcname(f"法定代表人身份证明书/{filename}"), content)

    # 证件类型标签映射
    _DOC_TYPE_LABELS: ClassVar[dict[str, str]] = {
        "id_card": "身份证",
        "business_license": "营业执照",
        "legal_rep_id_card": "法定代表人身份证",
        "org_code_cert": "组织机构代码证",
        "tax_reg_cert": "税务登记证",
        "other": "其他证件",
    }

    def _zip_add_client_identity_docs(
        self,
        zf: zipfile.ZipFile,
        *,
        our_parties: list[Any],
        media_root: str,
        missing_lines: list[str],
    ) -> None:
        for party in our_parties:
            client = getattr(party, "client", None)
            if not client:
                continue
            self._zip_add_single_client_docs(zf, client=client, media_root=media_root, missing_lines=missing_lines)

    def _zip_add_single_client_docs(
        self, zf: zipfile.ZipFile, *, client: Any, media_root: str, missing_lines: list[str]
    ) -> None:
        client_name = getattr(client, "name", "") or "未知当事人"
        safe_client_name = self._safe_name(client_name)

        try:
            identity_docs = self.client_service.get_identity_docs_by_client_internal(client.id)
        except Exception:
            logger.exception("操作失败")

            identity_docs: list[Any] = []

        for doc in identity_docs:
            self._zip_write_identity_doc(
                zf,
                doc=doc,
                client_name=client_name,
                safe_client_name=safe_client_name,
                media_root=media_root,
                missing_lines=missing_lines,
            )

        self._check_missing_required_docs( # type: ignore[no-any-return]
            identity_docs,
            client=client,
            client_name=client_name,
            missing_lines=missing_lines,
        )

    def _zip_write_identity_doc(
        self,
        zf: zipfile.ZipFile,
        *,
        doc: Any,
        client_name: str,
        safe_client_name: str,
        media_root: str,
        missing_lines: list[str],
    ) -> None:
        file_path = doc.file_path or ""
        if not file_path.strip():
            return
        abs_path = self._resolve_media_path(media_root, file_path)
        doc_label = self._DOC_TYPE_LABELS.get(doc.doc_type, doc.doc_type_display or doc.doc_type)
        if not abs_path or not StdPath(abs_path).exists():
            missing_lines.append(f"缺少{client_name}的{doc_label}")
            return
        arc_dir = f"当事人证件材料/{safe_client_name}"
        arc_name = self._safe_arcname(f"{arc_dir}/{StdPath(abs_path).name}")
        zf.write(abs_path, arcname=arc_name)

        def _check_missing_required_docs(
            identity_docs: list[Any], *, client: Any, client_name: str, missing_lines: list[str]
        ) -> None:
            doc_types = {doc.doc_type for doc in identity_docs}
            if getattr(client, "client_type", "") == "natural":
                if "id_card" not in doc_types:
                    missing_lines.append(f"缺少{client_name}的身份证")
            else:
                if "business_license" not in doc_types:
                    missing_lines.append(f"缺少{client_name}的营业执照")
                if "legal_rep_id_card" not in doc_types:
                    missing_lines.append(f"缺少{client_name}的法定代表人身份证")

    def _zip_add_lawyer_licenses(
        self,
        zf: zipfile.ZipFile,
        *,
        case: Any,
        missing_lines: list[str],
    ) -> None:
        try:
            assignments = list(case.assignments.select_related("lawyer").all())
        except Exception:
            logger.exception("操作失败")

            assignments: list[Any] = []

        seen: set[int] = set()
        for assignment in assignments:
            lawyer = getattr(assignment, "lawyer", None)
            lawyer_id = getattr(lawyer, "id", None)
            if not lawyer or not lawyer_id or lawyer_id in seen:
                continue
            seen.add(int(lawyer_id))

            lawyer_name = getattr(lawyer, "real_name", None) or getattr(lawyer, "username", "") or f"律师{lawyer_id}"
            license_field = getattr(lawyer, "license_pdf", None)
            if not license_field:
                missing_lines.append(f"缺少{lawyer_name}的律师执业证")
                continue
            if not getattr(license_field, "name", ""):
                missing_lines.append(f"缺少{lawyer_name}的律师执业证")
                continue

            ext = StdPath(getattr(license_field, "name", "") or "").suffix or ".pdf"
            arc_name = self._safe_arcname(f"律师执业证/律师证({lawyer_name}){ext}")
            try:
                with license_field.open("rb") as f:
                    zf.writestr(arc_name, f.read())
            except Exception:
                logger.exception("操作失败")

                missing_lines.append(f"缺少{lawyer_name}的律师执业证")

    def _zip_add_missing_markdown(self, zf: zipfile.ZipFile, *, missing_lines: list[str]) -> None:
        title = "# 当前授权手续所缺材料\n\n"
        if not missing_lines:
            body = "- 当前授权手续材料齐全\n"
        else:
            unique: list[Any] = []
            seen = set()
            for line in missing_lines:
                if line in seen:
                    continue
                seen.add(line)
                unique.append(line)
            body = "\n".join([f"- {x}" for x in unique]) + "\n"
        zf.writestr("当前授权手续所缺材料.md", title + body)

    def _resolve_media_path(self, media_root: str, file_path: str) -> str:
        return resolve_media_path(media_root, file_path)

    def _safe_arcname(self, name: str) -> str:
        return safe_arcname(name)

    def _safe_name(self, name: str) -> str:
        return safe_name(name)

    def _build_context(self, *, case: Any, client: Any | None = None) -> dict[str, Any]:
        context_data: dict[str, Any] = {"case": case}
        if client is not None:
            context_data["client"] = client
        return EnhancedContextBuilder().build_context(context_data) # type: ignore[no-any-return]

    def _build_power_of_attorney_context(self, *, case: Any, selected_clients: list[Any]) -> dict[str, Any]:
        context_data: dict[str, Any] = {
            "case": case,
            "selected_clients": selected_clients,
        }
        required_placeholders = [
            "授权委托书_代理事项",
            "案件案由",
            "指定日期",
            "年份",
        ]
        return EnhancedContextBuilder().build_context(context_data, required_placeholders=required_placeholders) # type: ignore[no-any-return]

    def _validate_power_of_attorney_context(self, context: dict[str, Any]) -> None:
        proxy_matters = (context.get("授权委托书_代理事项") or "").strip()
        if not proxy_matters:
            raise ValidationException(
                message=_("未匹配到代理事项规则"),
                code="PROXY_MATTER_RULE_NOT_MATCHED",
                errors={"placeholder": "授权委托书_代理事项"},
            )

    def _get_power_of_attorney_template_from_db(self) -> Any:
        """从数据库查找授权委托书模板(后备方案)"""
        template = (
            DocumentTemplate.objects.filter(name=TEMPLATE_NAME_POWER_OF_ATTORNEY, is_active=True)
            .order_by("-updated_at")
            .first()
        )
        if not template:
            raise ValidationException(
                message=_("未找到%(n)s模板(请在后台上传/启用名称为'%(n)s'的模板)") % {"n": TEMPLATE_NAME_POWER_OF_ATTORNEY},
                code="TEMPLATE_NOT_FOUND",
                errors={"template_name": TEMPLATE_NAME_POWER_OF_ATTORNEY},
            )
        return template

    def _get_template_path_from_case_bindings(self, case_id: int, template_name: str) -> Path | None:
        """
        从案件绑定的模板中查找指定名称的模板路径

        优先查找案件绑定的模板(包括手动绑定和自动推荐),
        然后查找通用模板(根据案件类型、阶段匹配).

        Args:
            case_id: 案件ID
            template_name: 模板名称(如"所函"、"法定代表人身份证明书"、"授权委托书")

        Returns:
            模板文件路径,如果未找到则返回 None
        """
        # 1. 先从案件绑定记录中查找(通过 ServiceLocator)
        bindings = self.case_service.get_case_template_bindings_by_name_internal(case_id, template_name)
        if bindings:
            binding = bindings[0]
            # 需要获取模板文件路径,通过 document_service
            template_dto = self.document_service.get_template_by_id_internal(binding.template_id)
            if template_dto and template_dto.file_path:
                return Path(template_dto.file_path)

        # 2. 从通用模板中查找(根据案件类型、阶段匹配)
        case_dto = self.case_service.get_case_internal(case_id)
        if not case_dto:
            return None

        case_type = case_dto.case_type
        case_stage = case_dto.current_stage

        # 查询匹配的通用模板
        templates = DocumentTemplate.objects.filter(name=template_name, is_active=True, template_type=DocumentTemplateType.CASE)

        for template in templates:
            case_types = template.case_types or []
            case_stages = template.case_stages or []

            # 匹配案件类型
            type_match = "all" in case_types or case_type in case_types or not case_types

            # 匹配案件阶段
            stage_match = True
            if case_stage and case_stages:
                stage_match = "all" in case_stages or case_stage in case_stages

            if type_match and stage_match:
                location = template.get_file_location()
                if location:
                    return Path(location)

        return None

    def _has_template_in_case_bindings(self, case_id: int, template_name: str) -> bool:
        """
        检查案件绑定的模板中是否有指定名称的模板

        Args:
            case_id: 案件ID
            template_name: 模板名称

        Returns:
            是否存在该模板
        """
        template_path = self._get_template_path_from_case_bindings(case_id, template_name)
        return template_path is not None

    def _get_template_path(self, template: DocumentTemplate) -> Path:
        location = (template.get_file_location() or "").strip()
        if not location:
            raise ValidationException(
                message=_("模板文件路径为空"),
                code="TEMPLATE_FILE_EMPTY",
                errors={"template_id": str(cast(int, template.pk))}, # type: ignore[no-any-return]
            )
        return Path(location)

    def _get_our_client(self, case: Any, client_id: int) -> Any:
        try:
            parties = list(case.parties.select_related("client").all())
        except Exception as e:
            logger.warning(
                "获取案件当事人失败",
                extra={"case_id": getattr(case, "id", None), "error": str(e)},
            )
            parties: list[Any] = []

        for party in parties:
            client = getattr(party, "client", None)
            if not client:
                continue
            if getattr(client, "id", None) != client_id:
                continue
            if not getattr(client, "is_our_client", False):
                break
            return client

        raise ValidationException(
            message=_("我方当事人不存在或不合法"),
            code="INVALID_OUR_CLIENT",
            errors={"client_id": str(client_id)},
        )

    def _get_case(self, case_id: int) -> Any:
        case = self.case_service.get_case_model_internal(case_id)
        if not case:
            raise NotFoundError(
                message=_("案件不存在"),
                code="CASE_NOT_FOUND",
                errors={"case_id": str(case_id)},
            )
        return case

    def _get_our_legal_client(self, case: Any, client_id: int) -> Any:
        try:
            parties = list(case.parties.select_related("client").all())
        except Exception as e:
            logger.warning(
                "获取案件当事人失败",
                extra={"case_id": getattr(case, "id", None), "error": str(e)},
            )
            parties: list[Any] = []

        for party in parties:
            client = getattr(party, "client", None)
            if not client:
                continue
            if getattr(client, "id", None) != client_id:
                continue
            if not getattr(client, "is_our_client", False):
                break
            if getattr(client, "client_type", "") != "legal":
                break
            return client

        raise ValidationException(
            message=_("我方当事人法人不存在或不合法"),
            code="INVALID_LEGAL_CLIENT",
            errors={"client_id": str(client_id)},
        )

    def _render_template(self, template_path: Path, context: dict[str, Any]) -> bytes:
        if not template_path.exists():
            raise ValidationException(
                message=_("模板文件不存在: %(p)s") % {"p": template_path},
                code="TEMPLATE_NOT_FOUND",
                errors={"template_path": str(template_path)},
            )

        try:
            logger.info(
                "授权委托材料渲染模板", extra={"template_path": str(template_path), "keys": list(context.keys())}
            )
            from .pipeline import DocxRenderer

            return DocxRenderer().render(str(template_path), context)
        except Exception as e:
            logger.error("模板渲染失败", exc_info=True, extra={"template_path": str(template_path), "error": str(e)})
            raise ValidationException(
                message=_("模板渲染失败: %(e)s") % {"e": e},
                code="TEMPLATE_RENDER_ERROR",
                errors={"error": str(e)},
            ) from e

    def _build_authority_letter_filename(self, *, case_name: str) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        template_name = "所函"
        safe_case_name = case_name or "案件"
        return f"{template_name}({safe_case_name})V1_{date_str}.docx"

    def _build_legal_rep_certificate_filename(self, *, company_name: str) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        template_name = "法定代表人身份证明书"
        safe_company_name = company_name or "公司"
        return f"{template_name}({safe_company_name})V1_{date_str}.docx"

    def _build_power_of_attorney_filename(
        self, *, case: Any, selected_clients: list[Any], combined: bool = False
    ) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        template_name = "授权委托书"
        case_name = getattr(case, "name", "") or "案件"

        if combined:
            return f"{template_name}({case_name})V1_{date_str}.docx"

        if self._count_our_parties(case) <= 1:
            return f"{template_name}({case_name})V1_{date_str}.docx"

        client = selected_clients[0] if selected_clients else None
        client_name = getattr(client, "name", "") or "委托人"
        return f"{template_name}({client_name})({case_name})V1_{date_str}.docx"

    def _count_our_parties(self, case: Any) -> int:
        try:
            parties = list(case.parties.select_related("client").all())
        except Exception:
            logger.exception("操作失败")

            return 0
        count = 0
        for party in parties:
            client = getattr(party, "client", None)
            if client and getattr(client, "is_our_client", False):
                count += 1
        return count
