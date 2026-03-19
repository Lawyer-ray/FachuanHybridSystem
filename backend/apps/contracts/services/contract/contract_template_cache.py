"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any, cast

from django.core.cache import cache

from apps.core.infrastructure import CacheKeys


def _get_cache_version(version_key: str) -> int:
    return int(cache.get(version_key) or 1)


logger = logging.getLogger("apps.contracts")

# 缓存配置
TEMPLATE_CACHE_TIMEOUT = 3600  # 1小时
TEMPLATE_CACHE_PREFIX = "contract_template"


class ContractTemplateCache:
    """
    合同模板缓存服务

    职责:
    - 管理合同模板的缓存键生成
    - 提供模板数据的缓存存取方法
    - 支持按案件类型清除缓存
    - 支持清除所有缓存

    缓存策略:
        - 按案件类型缓存模板查询结果
        - 缓存过期时间:1小时
        - 缓存键格式:contract_template:{case_type}:{query_type}:{version}
    """

    def _get_document_version(self) -> int:
        return _get_cache_version(CacheKeys.documents_matching_version_document_templates())

    def _get_folder_version(self) -> int:
        return _get_cache_version(CacheKeys.documents_matching_version_folder_templates())

    def _get_cache_key(self, case_type: str, query_type: str, version: int = 0) -> str:
        return f"{TEMPLATE_CACHE_PREFIX}:{case_type}:{query_type}:{version}"

    def get_document_templates(self, case_type: str) -> list[dict[str, Any]] | None:
        """获取缓存的文书模板"""
        cache_key = self._get_cache_key(case_type, "document_templates", self._get_document_version())
        return cast(list[dict[str, Any]] | None, cache.get(cache_key))

    def set_document_templates(self, case_type: str, templates: list[dict[str, Any]]) -> None:
        """缓存文书模板"""
        cache_key = self._get_cache_key(case_type, "document_templates", self._get_document_version())
        cache.set(cache_key, templates, TEMPLATE_CACHE_TIMEOUT)
        logger.debug("缓存文书模板: %s, 数量: %d", cache_key, len(templates))

    def get_folder_templates(self, case_type: str) -> list[dict[str, Any]] | None:
        """获取缓存的文件夹模板"""
        cache_key = self._get_cache_key(case_type, "folder_templates", self._get_folder_version())
        return cast(list[dict[str, Any]] | None, cache.get(cache_key))

    def set_folder_templates(self, case_type: str, templates: list[dict[str, Any]]) -> None:
        """缓存文件夹模板"""
        cache_key = self._get_cache_key(case_type, "folder_templates", self._get_folder_version())
        cache.set(cache_key, templates, TEMPLATE_CACHE_TIMEOUT)
        logger.debug("缓存文件夹模板: %s, 数量: %d", cache_key, len(templates))

    def get_template_check(self, case_type: str) -> dict[str, bool] | None:
        """获取缓存的模板检查结果"""
        cache_key = self._get_cache_key(case_type, "check_templates", self._get_document_version())
        return cast(dict[str, bool] | None, cache.get(cache_key))

    def set_template_check(self, case_type: str, result: dict[str, bool]) -> None:
        """缓存模板检查结果"""
        cache_key = self._get_cache_key(case_type, "check_templates", self._get_document_version())
        cache.set(cache_key, result, TEMPLATE_CACHE_TIMEOUT)
        logger.debug("缓存模板检查结果: %s, 结果: %s", cache_key, result)

    def clear_cache_for_case_type(self, case_type: str) -> None:
        """清除特定案件类型的所有缓存（兼容旧键格式）"""
        # 清除当前版本的缓存键
        doc_ver = self._get_document_version()
        folder_ver = self._get_folder_version()
        cache.delete_many(
            [
                self._get_cache_key(case_type, "document_templates", doc_ver),
                self._get_cache_key(case_type, "folder_templates", folder_ver),
                self._get_cache_key(case_type, "check_templates", doc_ver),
            ]
        )
        logger.info("清除案件类型 %s 的模板缓存", case_type)

    def clear_all_cache(self) -> None:
        """清除所有模板缓存"""
        from apps.core.enums import CaseType

        for case_type_choice in CaseType.choices:
            case_type = case_type_choice[0]
            self.clear_cache_for_case_type(case_type)

        logger.info("清除所有模板缓存")
