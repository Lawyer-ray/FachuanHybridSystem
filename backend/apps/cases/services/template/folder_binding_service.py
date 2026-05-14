"""Business logic services for case folder binding."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case, CaseFolderBinding
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.core.exceptions import NotFoundError, PermissionDenied
from apps.core.filesystem import (
    FolderBindingCrudService,
    FolderBrowsePolicy,
    FolderFilesystemService,
    FolderPathValidator,
)
from apps.core.models.enums import CaseType

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService, IDocumentService
    from apps.core.security.access_context import AccessContext

logger = logging.getLogger("apps.cases")


class CaseFolderBindingService(FolderBindingCrudService):
    """Manage case folder bindings and case-side storage subdirectories."""

    DEFAULT_SUBDIRS: ClassVar = {
        "case_documents": "案件文书",
        "trial_materials": "庭审材料",
        "judgments": "判决书",
        "execution_documents": "执行文书",
        "other_files": "其他文件",
    }
    LOG_ATTACHMENT_DEFAULT_SUBDIR: ClassVar = "案件日志附件"
    LOG_ATTACHMENT_PREFERRED_PATHS: ClassVar = [
        "4-邮件往来",
        "案件日志附件",
        "案件材料",
        "一审/1-立案材料/4-证据目录",
        "一审/1-立案材料/5-证据材料",
    ]
    LOG_ATTACHMENT_KEYWORDS: ClassVar = [
        "邮件",
        "往来",
        "日志",
        "附件",
        "证据",
        "材料",
    ]

    LOG_ATTACHMENT_FILENAME_RULES: ClassVar = [
        {
            "keywords": ["证据目录", "证据清单"],
            "exclude_keywords": ["聊天记录", "通话记录", "录音", "录像", "照片", "截图"],
            "preferred_paths": ["一审/1-立案材料/4-证据目录", "4-证据目录"],
            "fallback_subdir": "一审/1-立案材料/4-证据目录",
        },
        {
            "keywords": [
                "证据",
                "举证",
                "质证",
                "聊天记录",
                "通话记录",
                "录音",
                "录像",
                "截图",
                "照片",
                "转账记录",
                "付款记录",
                "流水",
                "发票",
                "收据",
            ],
            "exclude_keywords": ["目录", "清单"],
            "preferred_paths": ["一审/1-立案材料/5-证据材料", "证据材料"],
            "fallback_subdir": "一审/1-立案材料/5-证据材料",
        },
        {
            "keywords": [
                "财产保全申请书",
                "保全申请书",
                "诉讼保全申请书",
                "财产保全",
                "保全申请",
                "保函",
                "担保函",
            ],
            "preferred_paths": [
                "一审/1-立案材料/8-保全申请书及保函",
                "8-保全申请书及保函",
                "保全申请书及保函",
                "保函",
            ],
            "fallback_subdir": "一审/1-立案材料/8-保全申请书及保函",
        },
        {
            "keywords": ["起诉状", "起诉书", "答辩状", "答辩书", "上诉状", "申请书"],
            "exclude_keywords": ["保全", "保函", "先行给付", "暂缓送达"],
            "preferred_paths": ["一审/1-立案材料/1-起诉材料", "起诉材料"],
            "fallback_subdir": "一审/1-立案材料/1-起诉材料",
        },
        {
            "keywords": ["庭审笔录", "庭审", "开庭", "质证笔录"],
            "preferred_paths": ["一审/2-庭审材料", "庭审材料"],
            "fallback_subdir": "一审/2-庭审材料",
        },
        {
            "keywords": ["判决书", "裁定书", "调解书"],
            "preferred_paths": ["一审/3-裁判文书", "裁判文书"],
            "fallback_subdir": "一审/3-裁判文书",
        },
        {
            "keywords": ["委托书", "授权", "律师函"],
            "preferred_paths": ["1-律师资料/1-授权委托", "1-律师资料/1-合同", "1-律师资料"],
            "fallback_subdir": "1-律师资料/1-授权委托",
        },
        {
            "keywords": ["送达", "快递", "邮寄", "邮件", "回执"],
            "preferred_paths": ["4-邮件往来", "案件日志附件"],
            "fallback_subdir": "4-邮件往来",
        },
    ]

    binding_model = CaseFolderBinding
    owner_model = Case
    owner_rel_field: str = "case"
    owner_id_field: str = "case_id"
    owner_label: str = "案件"

    def __init__(
        self,
        document_service: IDocumentService | None = None,
        case_service: ICaseService | None = None,
        filesystem_service: FolderFilesystemService | None = None,
        path_validator: FolderPathValidator | None = None,
        browse_policy: FolderBrowsePolicy | None = None,
    ) -> None:
        super().__init__(
            filesystem_service=filesystem_service,
            path_validator=path_validator,
            browse_policy=browse_policy,
            roots_setting_name="FOLDER_BROWSE_ROOTS",
            fallback_roots_setting_name="CONTRACT_FOLDER_BROWSE_ROOTS",
        )
        self._document_service = document_service
        self._case_service = case_service
        self._access_policy: CaseAccessPolicy | None = None

    @property
    def document_service(self) -> IDocumentService:
        if self._document_service is None:
            raise RuntimeError("CaseFolderBindingService.document_service 未注入")
        return self._document_service

    @property
    def case_service(self) -> ICaseService:
        if self._case_service is None:
            raise RuntimeError("CaseFolderBindingService.case_service 未注入")
        return self._case_service

    @property
    def access_policy(self) -> CaseAccessPolicy:
        if self._access_policy is None:
            self._access_policy = CaseAccessPolicy()
        return self._access_policy

    def _require_case_access(
        self,
        case_id: int,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> Case:
        case = self._get_case_internal(case_id)
        if not case:
            raise NotFoundError(
                message=_("案件不存在"),
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {case_id} 的案件不存在"},
            )

        self.access_policy.ensure_access(
            case_id=case.id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            case=case,
            message=_("无权限访问此案件"),
        )
        return case

    def _require_case_access_ctx(self, case_id: int, ctx: AccessContext) -> Case:
        return self._require_case_access(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def require_admin(self, ctx: AccessContext) -> None:
        user = ctx.user
        if not user or not getattr(user, "is_authenticated", False):
            raise PermissionDenied(_("需要登录"))

    def _get_owner(self, *, owner_id: int) -> Case:
        case = self._get_case_internal(owner_id)
        if not case:
            raise NotFoundError(
                message=_("案件不存在"),
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {owner_id} 的案件不存在"},
            )
        return case

    def _require_owner(
        self,
        *,
        owner_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        **kwargs: Any,
    ) -> Case:
        return self._require_case_access(
            case_id=owner_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def _resolve_subdir_path(self, *, owner_type: str, subdir_key: str) -> str | None:
        try:
            folder_node_path = self.document_service.get_folder_binding_path(owner_type, subdir_key)
            if not folder_node_path:
                return None

            from apps.core.filesystem.folder_node_path import normalize_folder_node_path

            return normalize_folder_node_path(folder_node_path)
        except Exception:
            logger.exception("resolve_subdir_path_failed", extra={"case_type": owner_type, "subdir_key": subdir_key})
            raise

    @transaction.atomic
    def create_binding(  # type: ignore[override]
        self,
        case_id: int,
        folder_path: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseFolderBinding:
        return cast(
            CaseFolderBinding,
            super().create_binding(
                owner_id=case_id,
                folder_path=folder_path,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    @transaction.atomic
    def create_binding_ctx(self, case_id: int, folder_path: str, ctx: AccessContext) -> CaseFolderBinding:
        return self.create_binding(
            case_id=case_id,
            folder_path=folder_path,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    @transaction.atomic
    def update_binding(  # type: ignore[override]
        self,
        case_id: int,
        folder_path: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseFolderBinding:
        return self.create_binding(
            case_id,
            folder_path,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    @transaction.atomic
    def update_binding_ctx(self, case_id: int, folder_path: str, ctx: AccessContext) -> CaseFolderBinding:
        return self.update_binding(
            case_id=case_id,
            folder_path=folder_path,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    @transaction.atomic
    def delete_binding(  # type: ignore[override]
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> bool:
        return super().delete_binding(
            owner_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    @transaction.atomic
    def delete_binding_ctx(self, case_id: int, ctx: AccessContext) -> bool:
        return self.delete_binding(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def get_binding(  # type: ignore[override]
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseFolderBinding | None:
        return super().get_binding(
            owner_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def get_binding_ctx(self, case_id: int, ctx: AccessContext) -> CaseFolderBinding | None:
        return self.get_binding(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def save_file_to_bound_folder(  # type: ignore[override]
        self,
        case_id: int,
        file_content: bytes,
        file_name: str,
        subdir_key: str = "case_documents",
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> str | None:
        return super().save_file_to_bound_folder(
            owner_id=case_id,
            file_content=file_content,
            file_name=file_name,
            subdir_key=subdir_key,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def extract_zip_to_bound_folder(  # type: ignore[override]
        self,
        case_id: int,
        zip_content: bytes,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> str | None:
        return super().extract_zip_to_bound_folder(
            owner_id=case_id,
            zip_content=zip_content,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def _get_case_internal(self, case_id: int) -> Case | None:
        try:
            return Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            return None

    def _get_binding_record(self, *, case_id: int) -> CaseFolderBinding | None:
        return CaseFolderBinding.objects.filter(case_id=case_id).first()

    def get_contract_folder_path(self, case_id: int) -> str | None:
        try:
            case = Case.objects.select_related("contract__folder_binding").get(pk=case_id)
        except Case.DoesNotExist:
            return None
        if not case.contract_id or not case.contract:
            return None
        contract = case.contract
        if not hasattr(contract, "folder_binding") or not contract.folder_binding:
            return None
        return contract.folder_binding.folder_path

    def check_and_repair_contract_path(self, binding: CaseFolderBinding) -> bool:
        contract_binding = self._get_contract_binding(binding)
        if contract_binding is None:
            return False
        _, auto_repaired = self.check_and_repair_path(contract_binding)
        return auto_repaired

    def _get_contract_binding(self, binding: CaseFolderBinding) -> Any | None:
        try:
            case = binding.case
            if not case.contract_id or not case.contract:
                return None
            contract = case.contract
            if not hasattr(contract, "folder_binding") or not contract.folder_binding:
                return None
            return contract.folder_binding
        except (AttributeError, TypeError, ValueError):
            return None

    def get_case_storage_root(self, owner_id: int) -> Path | None:
        binding = self._get_binding_record(case_id=owner_id)
        if not binding:
            return None

        is_accessible, _ = self.check_and_repair_path(binding)
        if not is_accessible:
            return None

        root = Path(binding.resolved_folder_path).expanduser().resolve()
        return self._resolve_business_root_from_binding(owner_id=owner_id, root=root)

    def list_bound_subdirs(
        self,
        owner_id: int,
        relative_path: str = "",
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        self._require_case_access(
            case_id=owner_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        binding = self._get_binding_record(case_id=owner_id)
        if not binding:
            raise NotFoundError(
                message=_("案件未绑定文件夹"),
                code="CASE_FOLDER_BINDING_NOT_FOUND",
                errors={"case_id": owner_id},
            )

        is_accessible, _ = self.check_and_repair_path(binding)
        if not is_accessible:
            raise NotFoundError(
                message=_("案件绑定文件夹不可用"),
                code="CASE_FOLDER_BINDING_UNAVAILABLE",
                errors={"folder_path": str(binding.folder_path or "")},
            )

        root = self._resolve_business_root_from_binding(
            owner_id=owner_id,
            root=Path(binding.resolved_folder_path).expanduser().resolve(),
        )
        current_path = ""
        current_dir = root
        raw_relative_path = str(relative_path or "").strip()
        if raw_relative_path:
            current_path = self.path_validator.normalize_relative_path(raw_relative_path)
            current_dir, current_path = self._resolve_existing_subdir_target(
                root=root,
                requested_path=current_path,
            )

        if not current_dir.exists() or not current_dir.is_dir():
            raise NotFoundError(
                message=_("子目录不存在"),
                code="CASE_STORAGE_SUBDIR_NOT_FOUND",
                errors={"relative_path": current_path or raw_relative_path},
            )

        entries: list[dict[str, str]] = []
        for child in sorted(current_dir.iterdir(), key=lambda item: item.name.lower()):
            if child.name.startswith(".") or not child.is_dir():
                continue
            entries.append(
                {
                    "name": child.name,
                    "relative_path": child.relative_to(root).as_posix(),
                }
            )

        parent_path: str | None = None
        if current_path:
            parts = current_path.split("/")
            parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""

        return {
            "root_path": root.as_posix(),
            "current_path": current_path,
            "parent_path": parent_path,
            "entries": entries,
        }

    def _resolve_business_root_from_binding(self, *, owner_id: int, root: Path) -> Path:
        case_root = self._find_generated_case_business_root(owner_id=owner_id, root=root)
        return case_root or root

    def _find_generated_case_business_root(self, *, owner_id: int, root: Path) -> Path | None:
        case = self.owner_model.objects.filter(id=owner_id).only("id", "name", "case_type").first()
        if not case:
            return None

        case_suffix = self._build_case_business_root_suffix(cast(Case, case))
        if not case_suffix:
            return None

        current_name = str(root.name or "").strip()
        if current_name.endswith(case_suffix):
            return root

        matches = [
            child
            for child in root.iterdir()
            if child.is_dir() and not child.name.startswith(".") and child.name.endswith(case_suffix)
        ]
        if not matches:
            return None

        matches.sort(key=lambda item: item.name)
        return matches[-1].resolve()

    def _build_case_business_root_suffix(self, case: Case) -> str:
        case_name = str(getattr(case, "name", "") or "").strip()
        case_type = str(getattr(case, "case_type", "") or "").strip()
        case_type_display = str(dict(CaseType.choices).get(case_type, case_type) or "").strip()
        if not case_name or not case_type_display:
            return ""
        return f"-[{case_type_display}]{case_name}"

    def _resolve_existing_subdir_target(self, *, root: Path, requested_path: str) -> tuple[Path, str]:
        normalized_path = self.path_validator.normalize_relative_path(requested_path)
        if not normalized_path:
            return root, ""

        target_dir = (root / normalized_path).resolve()
        self._ensure_directory_within_root(root, target_dir)
        if target_dir.exists() and target_dir.is_dir():
            return target_dir, normalized_path

        for parent in target_dir.parents:
            self._ensure_directory_within_root(root, parent)
            if parent == root:
                return root, ""
            if parent.exists() and parent.is_dir():
                return parent, parent.relative_to(root).as_posix()

        return root, ""

    def recommend_bound_subdir_for_log_attachment(
        self,
        owner_id: int,
        *,
        source_subfolder: str = "",
        file_name: str = "",
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, str]:
        normalized_source = self._normalize_optional_relative_path(source_subfolder)
        self._require_case_access(
            case_id=owner_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        binding = self._get_binding_record(case_id=owner_id)
        default_subdir = normalized_source or self.LOG_ATTACHMENT_DEFAULT_SUBDIR

        if not binding:
            return {
                "recommended_subdir": default_subdir,
                "matched_existing_subdir": normalized_source or "",
                "reason": "no_binding_default",
            }

        is_accessible, _ = self.check_and_repair_path(binding)
        if not is_accessible:
            return {
                "recommended_subdir": default_subdir,
                "matched_existing_subdir": normalized_source or "",
                "reason": "binding_unavailable_default",
            }

        root = self._resolve_business_root_from_binding(
            owner_id=owner_id,
            root=Path(binding.resolved_folder_path).expanduser().resolve(),
        )
        existing_subdirs = self._collect_relative_subdirs(root)

        file_name_match = self._recommend_subdir_by_file_name(
            existing_paths=existing_subdirs,
            file_name=file_name,
        )
        if file_name_match:
            return file_name_match

        if normalized_source:
            direct_match = self._match_preferred_existing_subdir(
                existing_paths=existing_subdirs,
                preferred_paths=[normalized_source],
            )
            if direct_match:
                return {
                    "recommended_subdir": direct_match,
                    "matched_existing_subdir": direct_match,
                    "reason": "source_subfolder_match",
                }
            return {
                "recommended_subdir": normalized_source,
                "matched_existing_subdir": "",
                "reason": "source_subfolder_default",
            }

        preferred_match = self._match_preferred_existing_subdir(
            existing_paths=existing_subdirs,
            preferred_paths=list(self.LOG_ATTACHMENT_PREFERRED_PATHS),
        )
        if preferred_match:
            return {
                "recommended_subdir": preferred_match,
                "matched_existing_subdir": preferred_match,
                "reason": "preferred_log_attachment_subdir",
            }

        matched = self._match_best_existing_subdir(
            existing_paths=existing_subdirs,
            label=self.LOG_ATTACHMENT_DEFAULT_SUBDIR,
            keywords=list(self.LOG_ATTACHMENT_KEYWORDS),
        )
        if matched:
            return {
                "recommended_subdir": matched,
                "matched_existing_subdir": matched,
                "reason": "matched_log_attachment_subdir",
            }

        return {
            "recommended_subdir": self.LOG_ATTACHMENT_DEFAULT_SUBDIR,
            "matched_existing_subdir": "",
            "reason": "default_log_attachment_subdir",
        }

    def _recommend_subdir_by_file_name(
        self,
        *,
        existing_paths: list[str],
        file_name: str,
    ) -> dict[str, str]:
        raw_file_name = str(file_name or "").strip()
        normalized_name = self._normalize_match_text(Path(raw_file_name).stem)
        if not normalized_name:
            return {}

        for rule in self.LOG_ATTACHMENT_FILENAME_RULES:
            keywords = [str(keyword or "").strip() for keyword in rule.get("keywords", []) if str(keyword or "").strip()]
            if not keywords:
                continue
            if not any(self._normalize_match_text(keyword) in normalized_name for keyword in keywords):
                continue

            exclude_keywords = [
                str(keyword or "").strip()
                for keyword in rule.get("exclude_keywords", [])
                if str(keyword or "").strip()
            ]
            if any(self._normalize_match_text(keyword) in normalized_name for keyword in exclude_keywords):
                continue

            match_keywords = list(dict.fromkeys([*keywords, *self._extract_file_name_keywords(raw_file_name)]))
            keyword_match = self._match_best_existing_subdir(
                existing_paths=existing_paths,
                label=raw_file_name,
                keywords=match_keywords,
            )
            if keyword_match:
                return {
                    "recommended_subdir": keyword_match,
                    "matched_existing_subdir": keyword_match,
                    "reason": "file_name_keyword_match",
                }

            preferred_match = self._match_preferred_existing_subdir(
                existing_paths=existing_paths,
                preferred_paths=[str(path or "").strip() for path in rule.get("preferred_paths", [])],
            )
            if preferred_match:
                return {
                    "recommended_subdir": preferred_match,
                    "matched_existing_subdir": preferred_match,
                    "reason": "file_name_rule_match",
                }

            fallback_subdir = self._normalize_optional_relative_path(str(rule.get("fallback_subdir", "") or "").strip())
            if fallback_subdir:
                return {
                    "recommended_subdir": fallback_subdir,
                    "matched_existing_subdir": "",
                    "reason": "file_name_rule_fallback",
                }

        generic_match = self._match_best_existing_subdir(
            existing_paths=existing_paths,
            label=str(file_name or "").strip(),
            keywords=self._extract_file_name_keywords(file_name),
        )
        if generic_match:
            return {
                "recommended_subdir": generic_match,
                "matched_existing_subdir": generic_match,
                "reason": "file_name_generic_match",
            }
        return {}

    def _extract_file_name_keywords(self, file_name: str) -> list[str]:
        stem = Path(str(file_name or "").strip()).stem
        if not stem:
            return []
        parts = [part.strip() for part in re.split(r"[\s_\-()（）【】\[\]、，,]+", stem) if part.strip()]
        expanded: list[str] = []
        for part in parts:
            expanded.append(part)
            if len(part) >= 2:
                expanded.append(part[:2])
        return list(dict.fromkeys(expanded))

    def _ensure_directory_within_root(self, root: Path, target: Path) -> None:
        try:
            target.relative_to(root)
        except ValueError:
            raise NotFoundError(
                message=_("目录超出允许范围"),
                code="CASE_STORAGE_SUBDIR_OUT_OF_ROOT",
                errors={"path": target.as_posix()},
            ) from None

    def _collect_relative_subdirs(self, root: Path) -> list[str]:
        results: list[str] = []
        for child in root.rglob("*"):
            if child.name.startswith(".") or not child.is_dir():
                continue
            try:
                relative = child.relative_to(root).as_posix()
            except ValueError:
                continue
            if relative:
                results.append(relative)
        return results

    def _match_preferred_existing_subdir(
        self,
        *,
        existing_paths: list[str],
        preferred_paths: list[str],
    ) -> str:
        if not existing_paths or not preferred_paths:
            return ""

        normalized_to_original = {
            self.path_validator.normalize_relative_path(path): path
            for path in existing_paths
            if str(path or "").strip()
        }
        for preferred in preferred_paths:
            normalized = self._normalize_optional_relative_path(str(preferred or "").strip())
            if normalized and normalized in normalized_to_original:
                return normalized_to_original[normalized]
        return ""

    def _match_best_existing_subdir(
        self,
        *,
        existing_paths: list[str],
        label: str,
        keywords: list[str],
    ) -> str:
        normalized_label = self._normalize_match_text(label)
        if not normalized_label and not keywords:
            return ""

        best_path = ""
        best_score = 0.0
        for path in existing_paths:
            normalized_path = self._normalize_match_text(path)
            if not normalized_path:
                continue
            score = self._score_subdir_match(label=label, normalized_path=normalized_path, keywords=keywords)
            if score > best_score or (score == best_score and score > 0 and self._is_more_specific_path(path, best_path)):
                best_score = score
                best_path = path
        return best_path if best_score >= 0.55 else ""

    def _score_subdir_match(
        self,
        *,
        label: str,
        normalized_path: str,
        keywords: list[str],
    ) -> float:
        normalized_label = self._normalize_match_text(label)
        if normalized_label and normalized_label in normalized_path:
            return 1.0

        label_tokens = [tok for tok in self._split_match_tokens(label) if len(tok) >= 2]
        label_score = 0.0
        if label_tokens:
            matched = sum(1 for tok in label_tokens if self._normalize_match_text(tok) in normalized_path)
            label_score = matched / len(label_tokens)

        valid_keywords = [kw for kw in keywords if len(str(kw or "").strip()) >= 2]
        keyword_score = 0.0
        if valid_keywords:
            normalized_keywords = [self._normalize_match_text(kw) for kw in valid_keywords if self._normalize_match_text(kw)]
            matched_keywords = [kw for kw in normalized_keywords if kw in normalized_path]
            if matched_keywords:
                longest_keyword = max(len(kw) for kw in normalized_keywords)
                best_match_length = max(len(kw) for kw in matched_keywords)
                keyword_score = best_match_length / longest_keyword if longest_keyword else 0.0
                if any(normalized_path.endswith(kw) for kw in matched_keywords):
                    keyword_score = max(keyword_score, 0.98)

        return max(label_score, keyword_score)

    def _split_match_tokens(self, text: str) -> list[str]:
        return [part for part in re.split(r"[\s/\\\-_()锛堬級]+", str(text or "").strip()) if part]

    def _normalize_match_text(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        return re.sub(r"[\s/\\\-_()锛堬級]+", "", raw).lower()

    def _normalize_optional_relative_path(self, relative_path: str) -> str:
        raw = str(relative_path or "").strip()
        if not raw:
            return ""
        return self.path_validator.normalize_relative_path(raw)

    def _split_match_tokens(self, text: str) -> list[str]:
        return [part for part in re.split(r"[\s/\\\-_()??]+", str(text or "").strip()) if part]

    def _normalize_match_text(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        return re.sub(r"[\s/\\\-_()??]+", "", raw).lower()

    def _is_more_specific_path(self, candidate: str, current: str) -> bool:
        candidate_depth = str(candidate or "").count("/")
        current_depth = str(current or "").count("/")
        if candidate_depth != current_depth:
            return candidate_depth > current_depth
        return len(str(candidate or "")) > len(str(current or ""))
