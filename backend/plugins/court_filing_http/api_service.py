"""一张网立案 — 纯 HTTP 接口版（异步）。

登录由外部传入 token，本模块只负责立案接口调用。
失败时抛出异常,由调用方决定是否回退到 Playwright 版。

注意：此文件为可插拔插件，不在 Git 仓库中。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import httpx

from .address_confirmation_mixin import AddressConfirmationMixin
from .constants import CASE_TYPE_CODES, PROVINCE_CODES, resolve_province_code
from .court_case_mixin import CourtCaseMixin
from .execution_validation_mixin import ExecutionValidationMixin
from .filing_flow_mixin import FilingFlowMixin
from .http_transport_mixin import HttpTransportMixin
from .material_mixin import MaterialMixin
from .party_mixin import PartyApiMixin

logger = logging.getLogger("plugins.court_filing_http")


class CourtZxfwFilingApiService(
    HttpTransportMixin,
    CourtCaseMixin,
    MaterialMixin,
    PartyApiMixin,
    ExecutionValidationMixin,
    FilingFlowMixin,
    AddressConfirmationMixin,
):
    """纯接口版一张网立案服务（异步）。"""

    def __init__(self, token: str) -> None:
        self._token = token
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": token,
                "Content-Type": "application/json",
                "Origin": "https://zxfw.court.gov.cn",
                "Referer": "https://zxfw.court.gov.cn/zxfw/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
                ),
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> CourtZxfwFilingApiService:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    def __enter__(self) -> CourtZxfwFilingApiService:
        return self

    def __exit__(self, *_: Any) -> None:
        self._run_sync(self.close())

    @staticmethod
    def _run_sync(coro: Any) -> Any:
        """在独立线程中运行协程，避免与已有 event loop 冲突。"""
        result_box: dict[str, Any] = {}
        err_box: dict[str, BaseException] = {}

        def _target() -> None:
            try:
                result_box["v"] = asyncio.run(coro)
            except BaseException as exc:
                err_box["e"] = exc

        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join()
        if "e" in err_box:
            raise err_box["e"]
        return result_box.get("v")

    # ── 同步入口（供 Playwright 调用方使用） ──
    # 整个生命周期（创建 client → 调用 → 关闭）在同一个 event loop 中完成

    def file_civil_case_sync(self, case_data: dict[str, Any]) -> dict[str, Any]:
        async def _lifecycle() -> dict[str, Any]:
            async with CourtZxfwFilingApiService(self._token) as svc:
                return await svc._file(case_data, "民事一审")

        return self._run_sync(_lifecycle())

    def file_execution_sync(self, case_data: dict[str, Any]) -> dict[str, Any]:
        async def _lifecycle() -> dict[str, Any]:
            async with CourtZxfwFilingApiService(self._token) as svc:
                return await svc._file(case_data, "申请执行")

        return self._run_sync(_lifecycle())

    # ── 异步入口 ──

    async def file_civil_case(self, case_data: dict[str, Any]) -> dict[str, Any]:
        return await self._file(case_data, "民事一审")

    async def file_administrative_case(self, case_data: dict[str, Any]) -> dict[str, Any]:
        return await self._file(case_data, "行政一审")

    async def file_execution(self, case_data: dict[str, Any]) -> dict[str, Any]:
        return await self._file(case_data, "申请执行")

    async def _file(self, case_data: dict[str, Any], case_type: str) -> dict[str, Any]:
        province = case_data.get("province", "广东省")
        sfid = resolve_province_code(province)
        court_name: str = case_data["court_name"]
        ajlx = CASE_TYPE_CODES[case_type]
        is_exec = case_type == "申请执行"

        fyid = await self._lookup_court(sfid, court_name)
        logger.info("法院ID: %s → %s", court_name, fyid)

        layyid = await self._create_layy(fyid, ajlx, sfid, is_exec=is_exec)
        logger.info("立案申请ID: %s", layyid)

        await self._patch_case_type_specific(
            layyid=layyid,
            fyid=fyid,
            court_name=court_name,
            case_data=case_data,
            is_exec=is_exec,
        )
        await self._upload_materials(layyid=layyid, fyid=fyid, case_data=case_data, is_exec=is_exec)
        await self._generate_and_upload_address_confirmation(layyid=layyid, fyid=fyid)
        await self._write_parties_and_agents(layyid=layyid, fyid=fyid, case_data=case_data, is_exec=is_exec)

        execution_target_updated_keys: set[str] = set()
        if is_exec:
            execution_target_updated_keys = await self._update_execution_target_info(
                layyid=layyid,
                fyid=fyid,
                case_data=case_data,
            )

        await self._finalize_and_validate(
            layyid=layyid,
            case_data=case_data,
            is_exec=is_exec,
            execution_target_updated_keys=execution_target_updated_keys,
        )

        return {"success": True, "layyid": layyid, "message": f"{case_type}HTTP立案完成（未提交）"}
