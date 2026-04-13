from __future__ import annotations

import importlib
import logging
from types import ModuleType
from typing import Any, Protocol, cast

logger = logging.getLogger(__name__)


class PrivateWeikeApiAdapter(Protocol):
    def open_http_session(
        self,
        *,
        client: Any,
        username: str,
        password: str,
        login_url: str | None,
    ) -> Any: ...

    def search_cases_via_api(
        self,
        *,
        client: Any,
        session: Any,
        keyword: str,
        max_candidates: int,
        max_pages: int,
        offset: int = 0,
        advanced_query: list[dict[str, str]] | None = None,
        court_filter: str = "",
        cause_of_action_filter: str = "",
        date_from: str = "",
        date_to: str = "",
    ) -> list[Any]: ...


_PRIVATE_MODULE_PATHS: tuple[str, ...] = (
    "apps.legal_research.services.sources.weike_api_private.adapter",
    "apps.legal_research.services.sources.weike.api_private.adapter",
)
_CACHE_UNSET = object()
_adapter_cache: object | PrivateWeikeApiAdapter | None = _CACHE_UNSET


def _resolve_adapter(module: ModuleType) -> PrivateWeikeApiAdapter | None:
    candidate = getattr(module, "API_ADAPTER", module)
    if not callable(getattr(candidate, "open_http_session", None)):
        return None
    if not callable(getattr(candidate, "search_cases_via_api", None)):
        return None
    return cast(PrivateWeikeApiAdapter, candidate)


def get_private_weike_api() -> PrivateWeikeApiAdapter | None:
    global _adapter_cache
    if _adapter_cache is not _CACHE_UNSET:
        return cast(PrivateWeikeApiAdapter | None, _adapter_cache)

    _adapter_cache = None
    for module_path in _PRIVATE_MODULE_PATHS:
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            # Ignore expected "module not found" when private module/package is absent.
            missing_name = str(exc.name or "")
            if missing_name and module_path.startswith(missing_name):
                continue
            if missing_name == module_path:
                continue
            # Unexpected dependency missing inside private module should be visible.
            if missing_name:
                logger.exception("加载私有wk API模块失败", extra={"private_module_path": module_path})
            continue
        except Exception:
            logger.exception("加载私有wk API模块失败", extra={"private_module_path": module_path})
            continue

        adapter = _resolve_adapter(module)
        if adapter is None:
            logger.warning(
                "私有wk API模块缺少必需入口(open_http_session/search_cases_via_api)，已忽略",
                extra={"private_module_path": module_path},
            )
            continue

        _adapter_cache = adapter
        logger.info("已启用私有wk API模块", extra={"private_module_path": module_path})
        break

    return _adapter_cache
