"""Business logic services."""

from __future__ import annotations

"""
案由和法院数据服务层
处理案由和法院数据的加载、解析和搜索业务逻辑

支持数据库优先查询,当数据库为空时回退到 JSON 文件
"""

import json
import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from apps.core.exceptions import ValidationException
from apps.core.path import Path

logger = logging.getLogger("apps.cases")

if TYPE_CHECKING:
    from apps.core.protocols import ICauseCourtQueryService


class CauseCourtDataCache:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    @lru_cache(maxsize=128)  # noqa: B019 - 缓存类设计,实例生命周期与应用一致
    def load_json_file(self, filename: str) -> dict[str, Any]:
        file_path = self.data_dir / filename
        try:
            if not file_path.exists():
                logger.error(
                    f"JSON文件不存在: {filename}",
                    extra={"action": "load_json_file", "file_name": filename, "file_path": str(file_path)},
                )
                raise ValidationException(
                    message=f"数据文件不存在: {filename}", code="FILE_NOT_FOUND", errors={"filename": filename}
                )

            with open(str(file_path), encoding="utf-8") as f:
                data = json.load(f)

            logger.debug(
                f"成功加载JSON文件: {filename}",
                extra={
                    "action": "load_json_file",
                    "file_name": filename,
                    "data_keys": list(data.keys()) if isinstance(data, dict[str, Any]) else "list[Any]",
                },
            )

            return data

        except json.JSONDecodeError as e:
            logger.error(
                f"JSON文件解析失败: {filename}, 错误: {e}",
                extra={"action": "load_json_file", "file_name": filename, "error": str(e)},
            )
            raise ValidationException(
                message=f"数据文件格式错误: {filename}",
                code="JSON_PARSE_ERROR",
                errors={"filename": filename, "error": str(e)},
            ) from e
        except Exception as e:
            logger.error(
                f"加载JSON文件异常: {filename}, 错误: {e}",
                extra={"action": "load_json_file", "file_name": filename, "error": str(e)},
            )
            raise ValidationException(
                message=f"加载数据文件失败: {filename}",
                code="FILE_LOAD_ERROR",
                errors={"filename": filename, "error": str(e)},
            ) from e


class CauseCourtDataParser:
    def flatten_tree(self, data: dict[str, Any], result: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        if result is None:
            result = []

        if isinstance(data, dict[str, Any]) and "name" in data:
            node_info = {"id": data.get("id", ""), "name": data.get("name", "")}
            if node_info["name"].strip():
                result.append(node_info)

        if isinstance(data, dict[str, Any]) and "children" in data:
            children = data.get("children", [])
            if isinstance(children, list[Any]):
                for child in children:
                    self.flatten_tree(child, result)
        elif isinstance(data, list[Any]):
            for item in data:
                self.flatten_tree(item, result)

        return result

    def filter_by_query(self, items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        matching_items = []
        for item in items:
            name = item.get("name", "")
            if query in name:
                matching_items.append(item)

        def sort_key(item) -> tuple[Any, ...]:
            name = item.get("name", "")
            if name == query:
                return (0, name)
            if name.startswith(query):
                return (1, name)
            return (2, name)

        matching_items.sort(key=sort_key)
        return matching_items


class CauseCourtDbProvider:
    def __init__(self, *, cause_court_query_service: "ICauseCourtQueryService") -> None:
        self.cause_court_query_service = cause_court_query_service

    def has_active_causes(self) -> bool:
        try:
            return self.cause_court_query_service.has_active_causes_internal()
        except Exception as e:
            logger.warning(
                "数据库案由可用性检查失败,回退到 JSON",
                extra={"action": "has_active_causes", "error": str(e), "error_type": type(e).__name__},
            )
            return False

    def has_active_courts(self) -> bool:
        try:
            return self.cause_court_query_service.has_active_courts_internal()
        except Exception as e:
            logger.warning(
                "数据库法院可用性检查失败,回退到 JSON",
                extra={"action": "has_active_courts", "error": str(e), "error_type": type(e).__name__},
            )
            return False

    def search_causes(self, query: str, case_type: str | None, limit: int) -> list[dict[str, Any]]:
        return self.cause_court_query_service.search_causes_internal(query, case_type, limit)

    def search_courts(self, query: str, limit: int) -> list[dict[str, Any]]:
        return self.cause_court_query_service.search_courts_internal(query, limit)

    def list_causes_by_parent(self, parent_id: int | None) -> list[dict[str, Any]]:
        return self.cause_court_query_service.list_causes_by_parent_internal(parent_id)


class CauseCourtJsonProvider:
    def __init__(
        self,
        cache: CauseCourtDataCache,
        parser: CauseCourtDataParser,
        case_type_file_map: dict[str, list[str]],
    ) -> None:
        self.cache = cache
        self.parser = parser
        self.case_type_file_map = case_type_file_map

    def get_causes_by_type(self, case_type: str) -> list[dict[str, Any]]:
        filenames = self.case_type_file_map[case_type]
        if not filenames:
            logger.info(
                f"案件类型 {case_type} 不提供自动补全", extra={"action": "get_causes_by_type", "case_type": case_type}
            )
            return []

        all_causes = []
        for filename in filenames:
            try:
                data = self.cache.load_json_file(filename)
                causes = self.parser.flatten_tree(data)
                all_causes.extend(causes)

                logger.debug(
                    f"从 {filename} 加载了 {len(causes)} 个案由",
                    extra={"action": "get_causes_by_type", "file_name": filename, "cause_count": len(causes)},
                )

            except Exception as e:
                logger.error(
                    f"加载案由文件失败: {filename}, 错误: {e}",
                    extra={"action": "get_causes_by_type", "file_name": filename, "error": str(e)},
                )
                continue

        logger.info(
            f"案件类型 {case_type} 共加载 {len(all_causes)} 个案由",
            extra={"action": "get_causes_by_type", "case_type": case_type, "total_causes": len(all_causes)},
        )

        return all_causes

    def search_causes(self, query: str, case_type: str | None, limit: int) -> list[dict[str, Any]]:
        try:
            if case_type:
                all_causes = self.get_causes_by_type(case_type)
            else:
                all_causes = []
                for ct in ["civil", "criminal", "administrative"]:
                    try:
                        causes = self.get_causes_by_type(ct)
                        all_causes.extend(causes)
                    except Exception as e:
                        logger.warning(
                            "加载案由失败,跳过该案件类型",
                            extra={
                                "action": "search_causes_from_json",
                                "case_type": ct,
                                "error": str(e),
                                "error_type": type(e).__name__,
                            },
                            exc_info=True,
                        )
                        continue

            matching_causes = self.parser.filter_by_query(all_causes, query)
            result = matching_causes[:limit]

            logger.debug(
                f"案由搜索完成: 关键词='{query}', 类型={case_type}, "
                f"找到={len(matching_causes)}个, 返回={len(result)}个",
                extra={
                    "action": "search_causes_from_json",
                    "query": query,
                    "case_type": case_type,
                    "total_matches": len(matching_causes),
                    "returned_count": len(result),
                },
            )

            return result

        except Exception:
            logger.exception("search_causes_from_json_failed", extra={"query": query, "case_type": case_type})
            raise

    def search_courts(self, query: str, limit: int) -> list[dict[str, Any]]:
        try:
            court_data = self.cache.load_json_file("法院.json")
            all_courts = self.parser.flatten_tree(court_data)
            matching_courts = self.parser.filter_by_query(all_courts, query)
            result = matching_courts[:limit]

            logger.debug(
                f"法院搜索完成: 关键词='{query}', 找到={len(matching_courts)}个, 返回={len(result)}个",
                extra={
                    "action": "search_courts_from_json",
                    "query": query,
                    "total_matches": len(matching_courts),
                    "returned_count": len(result),
                },
            )

            return result

        except Exception:
            logger.exception("search_courts_from_json_failed", extra={"query": query})
            raise


class CauseCourtDataService:
    """
    案由和法院数据服务

    职责:
    1. 根据案件类型加载对应的案由数据
    2. 提供案由和法院数据的搜索功能
    3. 递归解析JSON层级结构
    4. 缓存数据以提高性能
    5. 优先查询数据库,数据库为空时回退到 JSON 文件
    """

    # 案件类型到案由文件的映射
    CASE_TYPE_FILE_MAP: ClassVar = {
        "civil": ["民事案由.json"],
        "criminal": ["刑事案由.json"],
        "administrative": ["行政案由.json"],
        "execution": ["民事案由.json", "刑事案由.json", "行政案由.json"],
        "bankruptcy": [],  # 破产类型不提供自动补全
    }

    # 案件类型映射:将 execution 映射到多个数据库类型
    CASE_TYPE_DB_MAP: ClassVar = {
        "civil": ["civil"],
        "criminal": ["criminal"],
        "administrative": ["administrative"],
        "execution": ["civil", "criminal", "administrative"],
        "bankruptcy": [],
    }

    def __init__(
        self,
        db_provider: CauseCourtDbProvider | None = None,
        json_provider: CauseCourtJsonProvider | None = None,
        cache: CauseCourtDataCache | None = None,
        parser: CauseCourtDataParser | None = None,
    ) -> None:
        self.data_dir = Path(__file__).resolve().parents[3] / "core" / "static" / "core" / "data"
        self._db_provider = db_provider
        self._json_provider = json_provider
        self._cache = cache
        self._parser = parser

        logger.info(
            "初始化案由法院数据服务",
            extra={
                "action": "init_cause_court_data_service",
                "data_dir": str(self.data_dir),
                "case_type_mappings": list(self.CASE_TYPE_FILE_MAP.keys()),
            },
        )

    @property
    def cache(self) -> CauseCourtDataCache:
        if self._cache is None:
            self._cache = CauseCourtDataCache(self.data_dir)
        return self._cache

    @property
    def parser(self) -> CauseCourtDataParser:
        if self._parser is None:
            self._parser = CauseCourtDataParser()
        return self._parser

    @property
    def db_provider(self) -> CauseCourtDbProvider:
        if self._db_provider is None:
            from apps.core.dependencies.core import build_cause_court_query_service

            self._db_provider = CauseCourtDbProvider(cause_court_query_service=build_cause_court_query_service())
        return self._db_provider

    @property
    def json_provider(self) -> CauseCourtJsonProvider:
        if self._json_provider is None:
            self._json_provider = CauseCourtJsonProvider(
                cache=self.cache,
                parser=self.parser,
                case_type_file_map=self.CASE_TYPE_FILE_MAP,
            )
        return self._json_provider

    def get_causes_by_type(self, case_type: str) -> list[dict[str, Any]]:
        if case_type not in self.CASE_TYPE_FILE_MAP:
            logger.warning(
                f"无效的案件类型: {case_type}",
                extra={
                    "action": "get_causes_by_type",
                    "case_type": case_type,
                    "valid_types": list(self.CASE_TYPE_FILE_MAP.keys()),
                },
            )
            raise ValidationException(
                message=f"无效的案件类型: {case_type}",
                code="INVALID_CASE_TYPE",
                errors={"case_type": case_type, "valid_types": list(self.CASE_TYPE_FILE_MAP.keys())},
            )
        return self.json_provider.get_causes_by_type(case_type)

    def _flatten_tree(self, data: dict[str, Any], result: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        return self.parser.flatten_tree(data, result)

    def search_causes(self, query: str, case_type: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        if not query or not query.strip():
            logger.debug(
                "搜索关键词为空",
                extra={"action": "search_causes", "query": query, "case_type": case_type},
            )
            return []

        query = query.strip()
        if self.db_provider.has_active_causes():
            logger.debug(
                "使用数据库查询案由",
                extra={"action": "search_causes", "source": "database", "query": query, "case_type": case_type},
            )
            return self.db_provider.search_causes(query, case_type, limit)

        logger.debug(
            "数据库为空,回退到 JSON 文件查询案由",
            extra={"action": "search_causes", "source": "json", "query": query, "case_type": case_type},
        )
        return self.json_provider.search_causes(query, case_type, limit)

    def search_courts(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        if not query or not query.strip():
            logger.debug(
                "搜索关键词为空",
                extra={"action": "search_courts", "query": query},
            )
            return []

        query = query.strip()
        if self.db_provider.has_active_courts():
            logger.debug(
                "使用数据库查询法院",
                extra={"action": "search_courts", "source": "database", "query": query},
            )
            return self.db_provider.search_courts(query, limit)

        logger.debug(
            "数据库为空,回退到 JSON 文件查询法院",
            extra={"action": "search_courts", "source": "json", "query": query},
        )
        return self.json_provider.search_courts(query, limit)

    def get_causes_by_parent(self, parent_id: int | None = None) -> list[dict[str, Any]]:
        try:
            if not self.db_provider.has_active_causes():
                return []
            return self.db_provider.list_causes_by_parent(parent_id)
        except Exception:
            logger.exception("get_causes_by_parent_failed", extra={"parent_id": parent_id})
            raise

    def get_cause_by_id(self, cause_id: int) -> Optional[dict[str, Any] | None]:
        """根据 ID 获取案由信息

        Args:
            cause_id: 案由 ID

        Returns:
            案由信息字典,不存在则返回 None
        """
        from apps.core.interfaces import ServiceLocator

        cause_court_query_service = ServiceLocator.get_cause_court_query_service()
        return cause_court_query_service.get_cause_by_id_internal(cause_id)
