"""Business logic services."""

from __future__ import annotations

import logging
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, TypedDict, cast

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case, CaseAssignment, CaseNumber, CaseParty, SupervisingAuthority

from .wiring import get_case_filing_number_service, get_document_service

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from apps.core.interfaces import ICaseFilingNumberService, IDocumentService

logger = logging.getLogger(__name__)


JSONDict = dict[str, object]
ImportData = dict[str, object]


class MaterialViewPayload(TypedDict):
    party_types: list[JSONDict]
    non_party_types: list[JSONDict]
    our_parties: list[MaterialPartyPayload]
    opponent_parties: list[MaterialPartyPayload]
    authorities: list[AuthorityPayload]


class SimplePartyPayload(TypedDict):
    id: int
    name: str


class DetailPartyPayload(TypedDict):
    id: int
    name: str
    client_type: str
    legal_status: str | None
    legal_status_display: str


class MaterialPartyPayload(TypedDict):
    id: int
    name: str
    legal_status: str | None
    legal_status_display: str


class AuthorityPayload(TypedDict):
    id: int
    name: str
    authority_type: str
    authority_type_display: str


class CaseMaterialServiceProtocol(Protocol):
    def get_used_type_ids(self, *, case_id: int) -> list[int]: ...

    def get_material_types_by_category(
        self,
        *,
        category: str,
        law_firm_id: int | None,
        used_type_ids: list[int],
    ) -> list[JSONDict]: ...


class CaseImportServiceProtocol(Protocol):
    def import_one(self, data: ImportData) -> Case: ...


class CaseAdminService:
    """案件 Admin 服务"""

    def __init__(
        self,
        document_service: IDocumentService | None = None,
        filing_number_service: ICaseFilingNumberService | None = None,
    ) -> None:
        """
        构造函数支持依赖注入

            document_service: 文档服务实例(可选,用于依赖注入)
            filing_number_service: 建档编号服务实例(可选,用于依赖注入)
        """
        self._document_service = document_service
        self._filing_number_service = filing_number_service

    @property
    def document_service(self) -> IDocumentService:
        """
        延迟加载文档服务

        通过 ServiceLocator 获取 IDocumentService 实例,
        支持依赖注入以便于测试.

            IDocumentService 实例
        """
        if self._document_service is None:
            self._document_service = get_document_service()
        return self._document_service

    @property
    def filing_number_service(self) -> ICaseFilingNumberService:
        """
        延迟加载建档编号服务

        支持依赖注入以便于测试.

            FilingNumberService 实例
        """
        if self._filing_number_service is None:
            self._filing_number_service = get_case_filing_number_service()
        return self._filing_number_service

    def get_matched_folder_templates(self, case_type: str, legal_statuses: list[str] | None = None) -> str:
        """
        获取匹配的文件夹模板

            case_type: 案件类型
            legal_statuses: 案件的诉讼地位列表(我方当事人的诉讼地位)

            模板名称字符串,多个模板用"、"分隔
            如果查询失败返回 "查询失败"
        """
        try:
            if legal_statuses:
                return self.document_service.get_matched_folder_templates_with_legal_status(case_type, legal_statuses)
            return self.document_service.get_matched_folder_templates(case_type)
        except Exception:
            logger.exception(
                "get_matched_folder_templates_failed", extra={"case_type": case_type, "legal_statuses": legal_statuses}
            )
            return str(_("查询失败"))

    def get_matched_folder_templates_list(
        self, case_type: str, legal_statuses: list[str] | None = None
    ) -> list[JSONDict]:
        try:
            module = import_module("apps.documents.services.template.template_matching_service")
            template_matching_service_cls = module.TemplateMatchingService

            return cast(
                list[JSONDict],
                template_matching_service_cls().find_matching_case_folder_templates_list(
                    case_type=case_type,
                    legal_statuses=legal_statuses,
                ),
            )
        except Exception:
            logger.exception("get_matched_folder_templates_list_failed", extra={"case_type": case_type})
            return []

    def get_matched_case_file_templates(self, case_type: str, case_stage: str) -> list[JSONDict]:
        try:
            return cast(
                list[JSONDict],
                self.document_service.find_matching_case_file_templates(
                    case_type=case_type,
                    case_stage=case_stage,
                ),
            )
        except Exception:
            logger.exception(
                "get_matched_case_file_templates_failed", extra={"case_type": case_type, "case_stage": case_stage}
            )
            return []

    def get_case_file_sub_type_choices(self) -> list[tuple[str, str]]:
        """获取案件文件子类型选项。"""
        try:
            choices_module = import_module("apps.documents.models.choices")
            return list(choices_module.DocumentCaseFileSubType.choices)
        except Exception:
            logger.exception("get_case_file_sub_type_choices_failed")
            return []

    def get_case_file_templates_for_detail(self, case: Case) -> tuple[list[JSONDict], str]:
        """获取详情页案件文件模板与缺失原因。"""
        if not case.case_type:
            return [], str(_("未设置案件类型"))
        if not case.current_stage:
            return [], str(_("未设置案件阶段"))
        return self.get_matched_case_file_templates(case_type=case.case_type, case_stage=case.current_stage), ""

    def build_our_legal_entities(self, case: Case) -> list[SimplePartyPayload]:
        """构建我方主体（法人）视图数据。"""
        return [
            {"id": party.client.id, "name": party.client.name}
            for party in case.parties.all()
            if getattr(party.client, "is_our_client", False) and getattr(party.client, "client_type", "") == "legal"
        ]

    def build_our_parties(self, case: Case) -> list[DetailPartyPayload]:
        """构建我方当事人视图数据。"""
        parties: list[DetailPartyPayload] = []
        for party in case.parties.all():
            client = party.client
            if not getattr(client, "is_our_client", False):
                continue
            parties.append(
                {
                    "id": client.id,
                    "name": client.name,
                    "client_type": getattr(client, "client_type", "") or "",
                    "legal_status": getattr(party, "legal_status", None),
                    "legal_status_display": (
                        getattr(party, "get_legal_status_display", lambda: "")()
                        if getattr(party, "legal_status", None)
                        else ""
                    ),
                }
            )
        return parties

    def build_respondents(self, case: Case) -> list[SimplePartyPayload]:
        """构建对方当事人视图数据。"""
        return [
            {"id": party.client.id, "name": party.client.name}
            for party in case.parties.all()
            if not getattr(party.client, "is_our_client", False)
        ]

    def build_material_view_parties(self, case: Case) -> tuple[list[MaterialPartyPayload], list[MaterialPartyPayload]]:
        """构建材料页我方/对方当事人数据。"""
        our_parties: list[MaterialPartyPayload] = []
        opponent_parties: list[MaterialPartyPayload] = []
        for party in case.parties.all():
            client = party.client
            item: MaterialPartyPayload = {
                "id": party.id,
                "name": getattr(client, "name", "") or "",
                "legal_status": getattr(party, "legal_status", None),
                "legal_status_display": (
                    getattr(party, "get_legal_status_display", lambda: "")()
                    if getattr(party, "legal_status", None)
                    else ""
                ),
            }
            if getattr(client, "is_our_client", False):
                our_parties.append(item)
            else:
                opponent_parties.append(item)
        return our_parties, opponent_parties

    def build_material_view_authorities(self, case: Case) -> list[AuthorityPayload]:
        """构建材料页主管机关数据。"""
        return [
            {
                "id": authority.id,
                "name": authority.name or "",
                "authority_type": authority.authority_type or "",
                "authority_type_display": authority.get_authority_type_display() if authority.authority_type else "",
            }
            for authority in case.supervising_authorities.all().order_by("created_at")
        ]

    def get_case_with_admin_relations(self, case_id: int) -> Case | None:
        """按 admin 详情页需求查询案件及关联数据。"""
        from django.db.models import Prefetch

        from apps.cases.models import CaseLog

        try:
            return (  # type: ignore[no-any-return]
                Case.objects.select_related(
                    "contract",
                    "folder_binding",
                )
                .prefetch_related(
                    "case_numbers",
                    "supervising_authorities",
                    "parties__client",
                    "assignments__lawyer",
                    Prefetch(
                        "logs",
                        queryset=CaseLog.objects.select_related("actor").prefetch_related("attachments").order_by(
                            "-created_at"
                        ),
                    ),
                    "chats",
                )
                .get(pk=case_id)
            )
        except Case.DoesNotExist:
            return None

    def build_materials_view_payload(
        self,
        *,
        case: Case,
        material_service: CaseMaterialServiceProtocol,
        law_firm_id: int | None,
    ) -> MaterialViewPayload:
        """构建材料页所需数据。"""
        used_type_ids = material_service.get_used_type_ids(case_id=case.id)
        party_types = material_service.get_material_types_by_category(
            category="party",
            law_firm_id=law_firm_id,
            used_type_ids=used_type_ids,
        )
        non_party_types = material_service.get_material_types_by_category(
            category="non_party",
            law_firm_id=law_firm_id,
            used_type_ids=used_type_ids,
        )
        our_parties, opponent_parties = self.build_material_view_parties(case)
        authorities = self.build_material_view_authorities(case)
        return {
            "party_types": party_types,
            "non_party_types": non_party_types,
            "our_parties": our_parties,
            "opponent_parties": opponent_parties,
            "authorities": authorities,
        }

    def group_templates_by_sub_type(
        self,
        templates: list[JSONDict],
        sub_type_choices: list[tuple[str, str]],
    ) -> list[tuple[str, list[JSONDict]]]:
        """按案件文件子类型分组模板。"""
        hardcoded_sub_types = {"power_of_attorney_materials", "property_preservation_materials"}
        label_map = dict(sub_type_choices)
        groups: dict[str, list[JSONDict]] = {}
        for template in templates:
            sub_type = cast(str, template.get("case_sub_type", "other_materials"))
            if sub_type in hardcoded_sub_types:
                continue
            groups.setdefault(sub_type, []).append(template)
        order = [choice[0] for choice in sub_type_choices]
        return [(label_map.get(key, key), value) for key in order if (value := groups.get(key))]

    def detect_special_template_flags(self, unified_templates: list[JSONDict]) -> tuple[bool, bool]:
        """识别详情页特殊模板标记。"""
        has_preservation_template = any(
            template.get("function_code") == "preservation_application"
            or "财产保全申请书" in cast(str, template.get("name") or "")
            for template in unified_templates
        )
        has_delay_delivery_template = any(
            template.get("function_code") == "delay_delivery_application"
            or "暂缓送达申请书" in cast(str, template.get("name") or "")
            for template in unified_templates
        )
        return has_preservation_template, has_delay_delivery_template

    def serialize_queryset_for_export(self, queryset: QuerySet[Case]) -> list[JSONDict]:
        """序列化案件列表用于 Admin 导出。"""
        from apps.cases.services.case.case_admin_export_bridge import get_case_admin_export_prefetches
        from apps.cases.services.case.case_contract_export_bridge import (
            get_case_admin_contract_export_prefetches,
            serialize_contract_for_case_export,
        )
        from apps.cases.services.case.case_export_serializer_service import serialize_case_obj

        result: list[JSONDict] = []
        for case in queryset.prefetch_related(
            *get_case_admin_export_prefetches(),
            *get_case_admin_contract_export_prefetches(),
        ):
            data = serialize_case_obj(case)
            data["contract"] = serialize_contract_for_case_export(case.contract) if case.contract else None
            result.append(data)
        return result

    def collect_file_paths_for_export(self, queryset: QuerySet[Case]) -> list[str]:
        """收集案件导出相关文件路径。"""
        from apps.cases.services.case.case_admin_export_bridge import (
            collect_case_file_paths_for_export,
            get_case_admin_file_prefetches,
        )
        from apps.cases.services.case.case_contract_export_bridge import (
            collect_contract_file_paths_for_case_export,
            get_case_admin_contract_file_prefetches,
        )

        seen: set[str] = set()
        paths: list[str] = []

        def _add(path: str) -> None:
            if path and path not in seen:
                seen.add(path)
                paths.append(path)

        for case in queryset.prefetch_related(
            *get_case_admin_file_prefetches(),
            *get_case_admin_contract_file_prefetches(),
        ):
            if case.contract:
                collect_contract_file_paths_for_case_export(case.contract, _add)
            collect_case_file_paths_for_export(case, _add)
        return paths

    def import_cases_from_json_data(
        self,
        data_list: list[ImportData],
        *,
        case_import_service: CaseImportServiceProtocol,
    ) -> tuple[int, int, list[str]]:
        """执行 Admin JSON 导入并返回成功/跳过/错误统计。"""
        success = skipped = 0
        errors: list[str] = []

        for index, item in enumerate(data_list, 1):
            try:
                filing_number = item.get("filing_number")
                before = Case.objects.filter(filing_number=filing_number).exists() if filing_number else False
                case_import_service.import_one(item)
                if before:
                    skipped += 1
                else:
                    success += 1
            except Exception as exc:
                logger.exception("导入案件失败", extra={"index": index, "case_name": item.get("name", "?")})
                errors.append(f"[{index}] {item.get('name', '?')} ({type(exc).__name__}): {exc}")

        return success, skipped, errors

    @transaction.atomic
    def duplicate_case(self, case_id: int) -> Case:
        """
        复制案件及其所有关联数据(不复制日志和群聊)

            case_id: 原案件ID

            新创建的案件对象
        """
        # 获取原案件
        original = Case.objects.get(pk=case_id)

        # 复制主对象
        new_case = Case.objects.create(
            contract=original.contract,
            is_archived=False,  # 副本默认未建档
            name=f"{original.name} (副本)",
            status=original.status,
            effective_date=original.effective_date,
            cause_of_action=original.cause_of_action,
            target_amount=original.target_amount,
            case_type=original.case_type,
            current_stage=original.current_stage,
        )

        # 批量复制当事人
        parties_to_create = [
            CaseParty(
                case=new_case,
                client=party.client,
                legal_status=party.legal_status,
            )
            for party in original.parties.all()
        ]
        CaseParty.objects.bulk_create(parties_to_create)

        # 批量复制律师指派
        assignments_to_create = [
            CaseAssignment(
                case=new_case,
                lawyer=assignment.lawyer,
            )
            for assignment in original.assignments.all()
        ]
        CaseAssignment.objects.bulk_create(assignments_to_create)

        # 批量复制主管机关
        authorities_to_create = [
            SupervisingAuthority(
                case=new_case,
                name=authority.name,
                authority_type=authority.authority_type,
            )
            for authority in original.supervising_authorities.all()
        ]
        SupervisingAuthority.objects.bulk_create(authorities_to_create)

        # 批量复制案号
        case_numbers_to_create = [
            CaseNumber(
                case=new_case,
                number=case_number.number,
                remarks=case_number.remarks,
            )
            for case_number in original.case_numbers.all()
        ]
        CaseNumber.objects.bulk_create(case_numbers_to_create)

        # 注意:不复制 CaseLog(日志)和 CaseChat(群聊)

        return new_case

    @transaction.atomic
    def handle_case_filing_change(self, case_id: int, is_archived: bool) -> str | None:
        """
        处理案件建档状态变化

        业务逻辑:
        - 如果 is_archived=True 且 filing_number 为空,调用 FilingNumberService 生成编号
        - 如果 is_archived=True 且 filing_number 已存在,返回现有编号
        - 如果 is_archived=False,不修改 filing_number(保留在数据库中)

            case_id: 案件ID
            is_archived: 是否已建档

            str | None: 建档编号(如果已建档)

            NotFoundError: 案件不存在
            ValidationException: 数据验证失败

        Requirements: 5.1, 5.2, 6.1, 6.2, 6.3, 6.4
        """
        from apps.core.exceptions import NotFoundError

        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(
                message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID为 {case_id} 的案件不存在"}
            ) from None

        # 如果取消建档,不修改 filing_number(保留在数据库中)
        if not is_archived:
            logger.info(
                "取消案件建档,保留建档编号",
                extra={"case_id": case_id, "filing_number": case.filing_number, "action": "handle_case_filing_change"},
            )
            return None

        # 如果已建档且已有编号,返回现有编号
        if case.filing_number:
            logger.info(
                "案件已有建档编号,返回现有编号",
                extra={"case_id": case_id, "filing_number": case.filing_number, "action": "handle_case_filing_change"},
            )
            return case.filing_number

        # 如果已建档但没有编号,生成新编号
        created_year = case.start_date.year
        filing_number = self.filing_number_service.generate_case_filing_number_internal(
            case_id=case_id,
            case_type=case.case_type,  # type: ignore
            created_year=created_year,
        )

        # 保存编号到数据库
        case.filing_number = filing_number
        case.save(update_fields=["filing_number"])

        logger.info(
            "生成并保存案件建档编号",
            extra={"case_id": case_id, "filing_number": filing_number, "action": "handle_case_filing_change"},
        )

        return filing_number
