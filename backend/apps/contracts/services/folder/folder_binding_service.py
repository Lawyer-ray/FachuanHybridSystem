"""
合同文件夹绑定服务
处理合同与本地文件夹绑定的业务逻辑
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, ClassVar, cast

from apps.contracts.models import ArchiveClassificationRule, Contract, ContractFolderBinding
from apps.contracts.services.archive.category_mapping import get_archive_category
from apps.core.exceptions import ValidationException
from apps.core.filesystem import (
    FolderBindingCrudService,
    FolderBrowsePolicy,
    FolderFilesystemService,
    FolderPathValidator,
)
from apps.core.models.enums import CaseType
from apps.core.protocols import IDocumentTemplateBindingService

from .contract_subdir_path_resolver import ContractSubdirPathResolver

logger = logging.getLogger("apps.contracts")


class FolderBindingService(FolderBindingCrudService):
    """
    文件夹绑定服务

    职责:
    1. 管理合同与文件夹的绑定关系
    2. 验证文件夹路径格式
    3. 处理文件保存到绑定文件夹
    4. 管理子目录结构
    5. 根据文书模板绑定配置确定保存路径
    """

    # 默认子目录配置(仅在没有文书模板绑定配置时使用)
    DEFAULT_SUBDIRS: ClassVar = {
        "contract_documents": "合同文书",
        "supplementary_agreements": "补充协议",
        "other_files": "其他文件",
    }
    GENERIC_ARCHIVE_ROOT: ClassVar = "归档清单"
    MATERIAL_CATEGORY_DEFAULT_SUBDIRS: ClassVar = {
        "contract_original": "合同附件/合同正本",
        "supplementary_agreement": "合同附件/补充协议",
        "invoice": "合同附件/票据材料",
        "archive_document": "归档文书",
        "supervision_card": "监督卡",
        "authorization_material": "授权委托书",
        "case_material": "案件材料",
        "archive_upload": "归档上传",
    }
    MATERIAL_CATEGORY_PREFERRED_PATHS: ClassVar = {
        "contract_original": [
            "1-律师资料/1-合同",
            "合同附件/合同正本",
            "合同附件",
        ],
        "supplementary_agreement": [
            "1-律师资料/2-补充协议",
            "合同附件/补充协议",
        ],
        "invoice": [
            "1-律师资料/3-发票",
            "合同附件/票据材料",
        ],
        "archive_document": [
            "归档文书",
            "归档清单",
        ],
        "supervision_card": [
            "归档清单/办案服务质量监督卡",
            "归档清单/监督卡",
            "归档文书",
        ],
        "authorization_material": [
            "一审/1-立案材料/3-委托材料",
            "归档清单/授权委托证明材料",
            "授权委托书",
        ],
        "case_material": [
            "一审/1-立案材料/5-证据材料",
            "一审/1-立案材料/4-证据目录",
            "一审/1-立案材料",
            "案件材料",
        ],
        "archive_upload": [
            "归档清单",
            "归档文书",
            "归档上传",
        ],
    }
    MATERIAL_CATEGORY_KEYWORDS: ClassVar = {
        "contract_original": ["合同正本", "委托合同", "合同", "风险告知书"],
        "supplementary_agreement": ["补充协议", "补充", "协议"],
        "invoice": ["发票", "票据", "收费凭证", "收据"],
        "archive_document": ["归档文书", "归档", "档案"],
        "supervision_card": ["监督卡", "办案服务质量监督卡", "服务质量监督卡"],
        "authorization_material": ["授权委托书", "授权委托", "所函", "律师证", "身份证明"],
        "case_material": ["案件材料", "材料", "证据", "材料目录"],
        "archive_upload": ["归档上传", "上传", "归档"],
    }
    MATERIAL_CATEGORY_FILENAME_RULES: ClassVar = {
        "contract_original": [
            {
                "keywords": ["委托合同", "合同正本", "风险告知书", "合同"],
                "preferred_paths": ["1-律师资料/1-合同", "合同附件/合同正本", "合同附件"],
                "fallback_subdir": "1-律师资料/1-合同",
            },
        ],
        "supplementary_agreement": [
            {
                "keywords": ["补充协议", "补协", "补充合同"],
                "preferred_paths": ["1-律师资料/2-补充协议", "合同附件/补充协议"],
                "fallback_subdir": "1-律师资料/2-补充协议",
            },
        ],
        "invoice": [
            {
                "keywords": ["专票", "专用发票", "普票", "普通发票", "发票", "收据", "票据", "付款回单", "付款凭证", "转账回单"],
                "preferred_paths": ["1-律师资料/3-发票", "合同附件/票据材料"],
                "fallback_subdir": "1-律师资料/3-发票",
            },
        ],
        "authorization_material": [
            {
                "keywords": ["授权委托书", "授权委托", "所函", "律师证", "执业证", "身份证", "法定代表人身份证明"],
                "preferred_paths": ["一审/1-立案材料/3-委托材料", "归档清单/授权委托证明材料", "授权委托书"],
                "fallback_subdir": "一审/1-立案材料/3-委托材料",
            },
        ],
        "archive_document": [
            {
                "keywords": ["财产保全申请书", "保全申请书", "诉讼保全申请书", "财产保全", "保全申请", "保函", "担保函"],
                "preferred_paths": ["一审/1-立案材料/8-保全申请书及保函", "8-保全申请书及保函", "保全申请书及保函"],
                "fallback_subdir": "一审/1-立案材料/8-保全申请书及保函",
            },
            {
                "keywords": ["证据目录", "证据清单"],
                "preferred_paths": ["一审/1-立案材料/4-证据目录", "4-证据目录"],
                "fallback_subdir": "一审/1-立案材料/4-证据目录",
            },
            {
                "keywords": ["证据", "聊天记录", "通话记录", "录音", "录像", "截图", "照片", "转账记录", "付款记录", "流水", "发票", "收据"],
                "exclude_keywords": ["目录", "清单"],
                "preferred_paths": ["一审/1-立案材料/5-证据材料", "5-证据材料", "案件材料"],
                "fallback_subdir": "一审/1-立案材料/5-证据材料",
            },
            {
                "keywords": ["起诉状", "起诉书", "答辩状", "答辩书", "上诉状", "申请书"],
                "exclude_keywords": ["保全", "保函", "先行给付", "暂缓送达"],
                "preferred_paths": ["一审/1-立案材料/1-起诉状和反诉答辩状", "1-起诉材料", "起诉材料"],
                "fallback_subdir": "一审/1-立案材料/1-起诉状和反诉答辩状",
            },
            {
                "keywords": ["判决书", "裁定书", "调解书"],
                "preferred_paths": ["3-结案文书", "一审/3-结案文书", "裁判文书"],
                "fallback_subdir": "3-结案文书",
            },
        ],
        "case_material": [
            {
                "keywords": ["财产保全申请书", "保全申请书", "诉讼保全申请书", "财产保全", "保全申请", "保函", "担保函"],
                "preferred_paths": ["一审/1-立案材料/8-保全申请书及保函", "8-保全申请书及保函", "保全申请书及保函"],
                "fallback_subdir": "一审/1-立案材料/8-保全申请书及保函",
            },
            {
                "keywords": ["证据目录", "证据清单"],
                "preferred_paths": ["一审/1-立案材料/4-证据目录", "4-证据目录"],
                "fallback_subdir": "一审/1-立案材料/4-证据目录",
            },
            {
                "keywords": ["证据", "聊天记录", "通话记录", "录音", "录像", "截图", "照片", "转账记录", "付款记录", "流水", "发票", "收据"],
                "exclude_keywords": ["目录", "清单"],
                "preferred_paths": ["一审/1-立案材料/5-证据材料", "5-证据材料", "案件材料"],
                "fallback_subdir": "一审/1-立案材料/5-证据材料",
            },
            {
                "keywords": ["起诉状", "起诉书", "答辩状", "答辩书", "上诉状", "申请书"],
                "exclude_keywords": ["保全", "保函", "先行给付", "暂缓送达"],
                "preferred_paths": ["一审/1-立案材料/1-起诉状和反诉答辩状", "1-起诉材料", "起诉材料"],
                "fallback_subdir": "一审/1-立案材料/1-起诉状和反诉答辩状",
            },
            {
                "keywords": ["授权委托书", "授权委托", "所函", "律师证", "执业证", "身份证", "法定代表人身份证明"],
                "preferred_paths": ["一审/1-立案材料/3-委托材料", "归档清单/授权委托证明材料", "授权委托书"],
                "fallback_subdir": "一审/1-立案材料/3-委托材料",
            },
        ],
        "archive_upload": [
            {
                "keywords": ["财产保全申请书", "保全申请书", "诉讼保全申请书", "财产保全", "保全申请", "保函", "担保函"],
                "preferred_paths": ["一审/1-立案材料/8-保全申请书及保函", "8-保全申请书及保函", "保全申请书及保函"],
                "fallback_subdir": "一审/1-立案材料/8-保全申请书及保函",
            },
            {
                "keywords": ["证据目录", "证据清单"],
                "preferred_paths": ["一审/1-立案材料/4-证据目录", "4-证据目录"],
                "fallback_subdir": "一审/1-立案材料/4-证据目录",
            },
            {
                "keywords": ["证据", "聊天记录", "通话记录", "录音", "录像", "截图", "照片", "转账记录", "付款记录", "流水", "发票", "收据"],
                "exclude_keywords": ["目录", "清单"],
                "preferred_paths": ["一审/1-立案材料/5-证据材料", "5-证据材料", "案件材料"],
                "fallback_subdir": "一审/1-立案材料/5-证据材料",
            },
            {
                "keywords": ["起诉状", "起诉书", "答辩状", "答辩书", "上诉状", "申请书"],
                "exclude_keywords": ["保全", "保函", "先行给付", "暂缓送达"],
                "preferred_paths": ["一审/1-立案材料/1-起诉状和反诉答辩状", "1-起诉材料", "起诉材料"],
                "fallback_subdir": "一审/1-立案材料/1-起诉状和反诉答辩状",
            },
            {
                "keywords": ["授权委托书", "授权委托", "所函", "律师证", "执业证", "身份证", "法定代表人身份证明"],
                "preferred_paths": ["一审/1-立案材料/3-委托材料", "归档清单/授权委托证明材料", "授权委托书"],
                "fallback_subdir": "一审/1-立案材料/3-委托材料",
            },
        ],
    }

    binding_model = ContractFolderBinding
    owner_model = Contract
    owner_rel_field: str = "contract"
    owner_id_field: str = "contract_id"
    owner_label: str = "合同"

    def __init__(
        self,
        document_template_binding_service: IDocumentTemplateBindingService | None = None,
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
        self._subdir_path_resolver = ContractSubdirPathResolver(
            template_binding_service=document_template_binding_service,
        )

    def _resolve_subdir_path(self, *, owner_type: str, subdir_key: str) -> str | None:
        return self._subdir_path_resolver.resolve(case_type=owner_type, subdir_key=subdir_key)

    def _sanitize_file_name(self, file_name: str) -> str:
        """兼容旧测试入口：委托给统一路径校验器。"""
        return self.path_validator.sanitize_file_name(file_name)

    def _normalize_relative_path(self, relative_path: str) -> str:
        """兼容旧测试入口：委托给统一路径校验器。"""
        return self.path_validator.normalize_relative_path(relative_path)

    # 为了保持向后兼容,提供 contract_id 参数的便捷方法
    def create_binding_for_contract(self, contract_id: int, folder_path: str) -> Any:
        """为合同创建文件夹绑定(便捷方法)"""
        return self.create_binding(owner_id=contract_id, folder_path=folder_path)

    def update_binding_for_contract(self, contract_id: int, folder_path: str) -> Any:
        """为合同更新文件夹绑定(便捷方法)"""
        return self.update_binding(owner_id=contract_id, folder_path=folder_path)

    def delete_binding_for_contract(self, contract_id: int) -> bool:
        """删除合同的文件夹绑定(便捷方法)"""
        return self.delete_binding(owner_id=contract_id)

    def get_binding_for_contract(self, contract_id: int) -> ContractFolderBinding | None:
        """获取合同的文件夹绑定(便捷方法)"""
        binding = self.get_binding(owner_id=contract_id)
        return binding

    def get_contract_storage_root(self, owner_id: int) -> Path | None:
        """Return the actual business root used for contract attachments."""
        binding = self.get_binding(owner_id=owner_id)
        if not binding:
            return None

        is_accessible, _ = self.check_and_repair_path(binding)
        if not is_accessible:
            return None

        root = self._resolve_business_root_from_binding(
            owner_id=owner_id,
            root=Path(binding.folder_path).expanduser().resolve(),
        )
        return self._resolve_business_root_from_binding(owner_id=owner_id, root=root)

    def list_bound_subdirs(self, owner_id: int, relative_path: str = "") -> dict[str, Any]:
        """List subdirectories under the bound contract root only."""
        binding = self.get_binding(owner_id=owner_id)
        if not binding:
            raise ValidationException(message="未绑定合同文件夹", errors={"contract_id": owner_id})

        is_accessible, _ = self.check_and_repair_path(binding)
        if not is_accessible:
            raise ValidationException(message="绑定文件夹不可访问", errors={"folder_path": binding.folder_path})

        root = self._resolve_business_root_from_binding(
            owner_id=owner_id,
            root=Path(binding.folder_path).expanduser().resolve(),
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
        contract_root = self._find_generated_contract_business_root(owner_id=owner_id, root=root)
        return contract_root or root

    def _find_generated_contract_business_root(self, *, owner_id: int, root: Path) -> Path | None:
        contract = self.owner_model.objects.filter(id=owner_id).only("id", "name", "case_type").first()
        if not contract:
            return None

        contract_suffix = self._build_contract_business_root_suffix(cast(Contract, contract))
        if not contract_suffix:
            return None

        current_name = str(root.name or "").strip()
        if current_name.endswith(contract_suffix):
            return root

        matches = [
            child
            for child in root.iterdir()
            if child.is_dir() and not child.name.startswith(".") and child.name.endswith(contract_suffix)
        ]
        if not matches:
            return None

        matches.sort(key=lambda item: item.name)
        return matches[-1].resolve()

    def _build_contract_business_root_suffix(self, contract: Contract) -> str:
        contract_name = str(getattr(contract, "name", "") or "").strip()
        case_type = str(getattr(contract, "case_type", "") or "").strip()
        case_type_display = str(dict(CaseType.choices).get(case_type, case_type) or "").strip()
        if not contract_name or not case_type_display:
            return ""
        return f"-[{case_type_display}]{contract_name}"

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

    def recommend_bound_subdir_for_archive_item(
        self,
        owner_id: int,
        archive_item_name: str,
        archive_item_code: str = "",
        case_type: str = "",
    ) -> dict[str, str]:
        item_name = str(archive_item_name or "").strip()
        default_subdir = f"{self.GENERIC_ARCHIVE_ROOT}/{item_name}" if item_name else self.GENERIC_ARCHIVE_ROOT

        binding = self.get_binding(owner_id=owner_id)
        if not binding:
            return {
                "recommended_subdir": default_subdir,
                "matched_existing_subdir": "",
                "reason": "no_binding_default",
            }

        is_accessible, _ = self.check_and_repair_path(binding)
        if not is_accessible:
            return {
                "recommended_subdir": default_subdir,
                "matched_existing_subdir": "",
                "reason": "binding_unavailable_default",
            }

        root = self._resolve_business_root_from_binding(
            owner_id=owner_id,
            root=Path(binding.folder_path).expanduser().resolve(),
        )
        archive_category = get_archive_category(str(case_type or ""))
        rule_keywords = self._load_rule_keywords(archive_category=archive_category, archive_item_code=archive_item_code)
        matched = self._match_best_existing_subdir(
            self._collect_relative_subdirs(root),
            item_name,
            rule_keywords=rule_keywords,
        )
        if matched:
            return {
                "recommended_subdir": matched,
                "matched_existing_subdir": matched,
                "reason": "matched_existing_subdir_with_rules" if rule_keywords else "matched_existing_subdir",
            }

        return {
            "recommended_subdir": default_subdir,
            "matched_existing_subdir": "",
            "reason": "default_archive_item_subdir",
        }

    def recommend_bound_subdir_for_material_category(
        self,
        owner_id: int,
        material_category: str,
        file_name: str = "",
    ) -> dict[str, str]:
        category = str(material_category or "").strip()
        default_subdir = str(self.MATERIAL_CATEGORY_DEFAULT_SUBDIRS.get(category) or "????")
        preferred_paths = list(self.MATERIAL_CATEGORY_PREFERRED_PATHS.get(category) or [])
        keywords = list(self.MATERIAL_CATEGORY_KEYWORDS.get(category) or [])
        primary_name = keywords[0] if keywords else default_subdir.split("/")[-1]

        binding = self.get_binding(owner_id=owner_id)
        if not binding:
            return {
                "recommended_subdir": default_subdir,
                "matched_existing_subdir": "",
                "reason": "no_binding_default",
            }

        is_accessible, _ = self.check_and_repair_path(binding)
        if not is_accessible:
            return {
                "recommended_subdir": default_subdir,
                "matched_existing_subdir": "",
                "reason": "binding_unavailable_default",
            }

        root = self._resolve_business_root_from_binding(
            owner_id=owner_id,
            root=Path(binding.folder_path).expanduser().resolve(),
        )
        existing_subdirs = self._collect_relative_subdirs(root)

        file_name_match = self._recommend_subdir_by_material_category_and_file_name(
            existing_paths=existing_subdirs,
            material_category=category,
            file_name=file_name,
        )
        if file_name_match:
            return file_name_match

        preferred_match = self._match_preferred_existing_subdir(
            existing_paths=existing_subdirs,
            preferred_paths=preferred_paths,
        )
        if preferred_match:
            return {
                "recommended_subdir": preferred_match,
                "matched_existing_subdir": preferred_match,
                "reason": "preferred_material_category_subdir",
            }

        matched = self._match_best_existing_subdir(
            existing_subdirs,
            primary_name,
            rule_keywords=keywords,
        )
        if matched:
            return {
                "recommended_subdir": matched,
                "matched_existing_subdir": matched,
                "reason": "matched_material_category_subdir",
            }

        return {
            "recommended_subdir": default_subdir,
            "matched_existing_subdir": "",
            "reason": "default_material_category_subdir",
        }

    def _recommend_subdir_by_material_category_and_file_name(
        self,
        *,
        existing_paths: list[str],
        material_category: str,
        file_name: str,
    ) -> dict[str, str]:
        raw_file_name = str(file_name or "").strip()
        normalized_name = self._normalize_match_text(Path(raw_file_name).stem)
        if not normalized_name:
            return {}

        rules = list(self.MATERIAL_CATEGORY_FILENAME_RULES.get(str(material_category or "").strip()) or [])
        for rule in rules:
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
                existing_paths,
                raw_file_name,
                rule_keywords=match_keywords,
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

            fallback_subdir = self._normalize_relative_path(str(rule.get("fallback_subdir", "") or "").strip())
            if fallback_subdir:
                return {
                    "recommended_subdir": fallback_subdir,
                    "matched_existing_subdir": "",
                    "reason": "file_name_rule_fallback",
                }

        generic_match = self._match_best_existing_subdir(
            existing_paths,
            raw_file_name,
            rule_keywords=self._extract_file_name_keywords(raw_file_name),
        )
        if generic_match:
            return {
                "recommended_subdir": generic_match,
                "matched_existing_subdir": generic_match,
                "reason": "file_name_generic_match",
            }
        return {}

    def _match_preferred_existing_subdir(
        self,
        *,
        existing_paths: list[str],
        preferred_paths: list[str],
    ) -> str:
        if not existing_paths or not preferred_paths:
            return ""

        normalized_to_original = {
            self._normalize_relative_path(path): path
            for path in existing_paths
            if str(path or "").strip()
        }
        for preferred in preferred_paths:
            normalized = self._normalize_relative_path(str(preferred or "").strip())
            if normalized and normalized in normalized_to_original:
                return normalized_to_original[normalized]
        return ""

    def save_file_for_contract(
        self, contract_id: int, file_content: bytes, file_name: str, subdir_key: str = "contract_documents"
    ) -> str | None:
        """为合同保存文件到绑定文件夹(便捷方法)"""
        return self.save_file_to_bound_folder(
            owner_id=contract_id,
            file_content=file_content,
            file_name=file_name,
            subdir_key=subdir_key,
        )

    def extract_zip_for_contract(self, contract_id: int, zip_content: bytes) -> str | None:
        """为合同解压 ZIP 到绑定文件夹(便捷方法)"""
        return self.extract_zip_to_bound_folder(contract_id=contract_id, zip_content=zip_content)

    def save_file_to_bound_folder(  # type: ignore[override]
        self,
        owner_id: int,
        file_content: bytes,
        file_name: str,
        subdir_key: str = "contract_documents",
    ) -> str | None:
        """保存文件到绑定文件夹（实现 IContractFolderBindingService 协议）"""
        return super().save_file_to_bound_folder(  # type: ignore[return-value]
                owner_id=owner_id,
                file_content=file_content,
                file_name=file_name,
                subdir_key=subdir_key,
            ),

    def extract_zip_to_bound_folder(self, contract_id: int, zip_content: bytes) -> str | None:  # type: ignore[override]
        """解压 ZIP 到绑定文件夹（实现 IContractFolderBindingService 协议）"""
        return super().extract_zip_to_bound_folder(owner_id=contract_id, zip_content=zip_content)

    def _ensure_directory_within_root(self, root: Path, target: Path) -> None:
        try:
            target.relative_to(root)
        except ValueError:
            raise ValidationException(message="子目录越界", errors={"path": target.as_posix()}) from None

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

    def _match_best_existing_subdir(
        self,
        existing_paths: list[str],
        archive_item_name: str,
        *,
        rule_keywords: list[str] | None = None,
    ) -> str:
        normalized_item = self._normalize_match_text(archive_item_name)
        if not normalized_item:
            return ""

        best_path = ""
        best_score = 0.0
        for path in existing_paths:
            normalized_path = self._normalize_match_text(path)
            if not normalized_path:
                continue
            score = self._score_subdir_match(archive_item_name, normalized_path, rule_keywords=rule_keywords or [])
            if score > best_score or (score == best_score and score > 0 and self._is_more_specific_path(path, best_path)):
                best_score = score
                best_path = path
        return best_path if best_score >= 0.55 else ""

    def _score_subdir_match(
        self,
        archive_item_name: str,
        normalized_path: str,
        *,
        rule_keywords: list[str],
    ) -> float:
        normalized_item = self._normalize_match_text(archive_item_name)
        if normalized_item in normalized_path:
            return 1.0
        item_tokens = [tok for tok in self._split_match_tokens(archive_item_name) if len(tok) >= 2]
        item_score = 0.0
        if item_tokens:
            matched = sum(1 for tok in item_tokens if self._normalize_match_text(tok) in normalized_path)
            item_score = matched / len(item_tokens)

        keyword_score = 0.0
        valid_rule_keywords = [kw for kw in rule_keywords if len(str(kw or "").strip()) >= 2]
        if valid_rule_keywords:
            normalized_keywords = [self._normalize_match_text(kw) for kw in valid_rule_keywords if self._normalize_match_text(kw)]
            matched_keywords = [kw for kw in normalized_keywords if kw in normalized_path]
            if matched_keywords:
                longest_keyword = max(len(kw) for kw in normalized_keywords)
                best_match_length = max(len(kw) for kw in matched_keywords)
                keyword_score = best_match_length / longest_keyword if longest_keyword else 0.0
                if any(normalized_path.endswith(kw) for kw in matched_keywords):
                    keyword_score = max(keyword_score, 0.98)

        return max(item_score, keyword_score)

    def _split_match_tokens(self, text: str) -> list[str]:
        return [part for part in re.split(r"[\s/\\\-_()（）]+", str(text or "").strip()) if part]

    def _normalize_match_text(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        return re.sub(r"[\s/\\\-_()（）]+", "", raw).lower()

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

    def _is_more_specific_path(self, candidate: str, current: str) -> bool:
        candidate_depth = str(candidate or "").count("/")
        current_depth = str(current or "").count("/")
        if candidate_depth != current_depth:
            return candidate_depth > current_depth
        return len(str(candidate or "")) > len(str(current or ""))

    def _load_rule_keywords(self, *, archive_category: str, archive_item_code: str) -> list[str]:
        if not archive_category or not archive_item_code:
            return []
        return list(
            ArchiveClassificationRule.objects.filter(
                archive_category=archive_category,
                archive_item_code=archive_item_code,
            )
            .order_by("-hit_count", "filename_keyword")
            .values_list("filename_keyword", flat=True)
        )
