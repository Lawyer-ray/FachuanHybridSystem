"""授权 / 保全材料下载端点的多栏兜底（入口 C）。

这些端点平时叫「下载」，但只要案件绑定了合同文件夹，它们就通过
`save_file_for_contract` / `extract_zip_for_contract` **真写盘**——多栏并答时
agent 调一次就替其它栏把文件盖掉。四条口径：

1. 带会话头 + 该会话多栏登记 → 409，且落盘服务一次都没被调用；
2. 带会话头 + 单栏 → 正常保存（返回 folder_path）；
3. 不带会话头 → 正常保存（律师在页面上点「生成」）；
4. 两个 ZIP 端点（`authorization/package`、`preservation/package`）不走
   `_save_or_download`，各自单点也要拦得住。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from django.test import RequestFactory

import apps.documents.api.authorization_material_api as auth_api
import apps.documents.api.preservation_materials_api as preserve_api
from apps.agent.services.approval.policy import clear_multi_lane_session, mark_multi_lane_session
from apps.agent.services.approval.write_guard import MULTI_LANE_WRITE_CODE
from apps.core.exceptions import ConflictError

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MULTI = "documents-multi-lane"
SINGLE = "documents-single-lane"


def _request(session_id: str | None) -> Any:
    headers = {"x-fachuan-session": session_id} if session_id else {}
    return RequestFactory().post("/documents/cases/2/x/download", headers=headers)


def _binding_service(saved_path: str | None = "/tmp/合同/材料.docx") -> MagicMock:
    service = MagicMock()
    service.save_file_for_contract.return_value = saved_path
    service.extract_zip_for_contract.return_value = saved_path
    return service


@pytest.fixture
def multi_session() -> Any:
    mark_multi_lane_session(MULTI)
    try:
        yield MULTI
    finally:
        clear_multi_lane_session(MULTI)


@pytest.fixture
def single_session() -> Any:
    mark_multi_lane_session(SINGLE)
    clear_multi_lane_session(SINGLE)
    return SINGLE


@pytest.mark.parametrize(
    ("module", "endpoint"),
    [
        (auth_api, "documents.authorization.save_or_download"),
        (preserve_api, "documents.preservation.save_or_download"),
    ],
)
class TestSaveOrDownload:
    @pytest.mark.asyncio
    async def test_multi_lane_agent_is_refused_before_writing(
        self, monkeypatch: pytest.MonkeyPatch, module: Any, endpoint: str, multi_session: str
    ) -> None:
        binding = _binding_service()
        monkeypatch.setattr(module, "_get_folder_binding_service", lambda: binding)

        with pytest.raises(ConflictError) as exc_info:
            await module._save_or_download(
                _request(multi_session),
                contract_id=1,
                case_id=2,
                content=b"docx",
                filename="材料.docx",
                content_type=DOCX,
            )

        assert exc_info.value.code == MULTI_LANE_WRITE_CODE
        assert exc_info.value.errors["endpoint"] == endpoint
        binding.save_file_for_contract.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_lane_agent_still_saves(
        self, monkeypatch: pytest.MonkeyPatch, module: Any, endpoint: str, single_session: str
    ) -> None:
        binding = _binding_service()
        monkeypatch.setattr(module, "_get_folder_binding_service", lambda: binding)

        result = await module._save_or_download(
            _request(single_session),
            contract_id=1,
            case_id=2,
            content=b"docx",
            filename="材料.docx",
            content_type=DOCX,
        )

        assert result["success"] is True
        assert result["folder_path"] == "/tmp/合同/材料.docx"
        binding.save_file_for_contract.assert_called_once()

    @pytest.mark.asyncio
    async def test_lawyer_without_header_still_saves(
        self, monkeypatch: pytest.MonkeyPatch, module: Any, endpoint: str, multi_session: str
    ) -> None:
        """页面上点「生成」没有会话头：别的会话多栏并答不影响律师本人操作。"""
        binding = _binding_service()
        monkeypatch.setattr(module, "_get_folder_binding_service", lambda: binding)

        result = await module._save_or_download(
            _request(None), contract_id=1, case_id=2, content=b"docx", filename="材料.docx", content_type=DOCX
        )

        assert result["success"] is True
        binding.save_file_for_contract.assert_called_once()


class TestAuthorizationPackage:
    def _patch(self, monkeypatch: pytest.MonkeyPatch, service: MagicMock, binding: MagicMock) -> None:
        monkeypatch.setattr(auth_api, "_require_case_contract", AsyncMock(return_value={"contract_id": 1}))
        monkeypatch.setattr(auth_api, "_get_authorization_material_generation_service", lambda: service)
        monkeypatch.setattr(auth_api, "_get_folder_binding_service", lambda: binding)

    @pytest.mark.asyncio
    async def test_multi_lane_agent_is_refused_before_generating(
        self, monkeypatch: pytest.MonkeyPatch, multi_session: str
    ) -> None:
        service = MagicMock()
        binding = _binding_service()
        self._patch(monkeypatch, service, binding)

        with pytest.raises(ConflictError) as exc_info:
            await auth_api.download_authorization_package(_request(multi_session), case_id=2)

        assert exc_info.value.code == MULTI_LANE_WRITE_CODE
        assert exc_info.value.errors["endpoint"] == "documents.authorization.package"
        service.generate_full_authorization_package.assert_not_called()
        binding.extract_zip_for_contract.assert_not_called()

    @pytest.mark.asyncio
    async def test_lawyer_without_header_still_saves(self, monkeypatch: pytest.MonkeyPatch, multi_session: str) -> None:
        service = MagicMock()
        service.generate_full_authorization_package.return_value = (b"zip", "授权材料.zip")
        binding = _binding_service()
        self._patch(monkeypatch, service, binding)

        result = await auth_api.download_authorization_package(_request(None), case_id=2)

        assert result["success"] is True
        assert result["filename"] == "授权材料.zip"
        binding.extract_zip_for_contract.assert_called_once()


class TestPreservationPackage:
    def _patch(self, monkeypatch: pytest.MonkeyPatch, service: MagicMock, binding: MagicMock) -> None:
        monkeypatch.setattr(preserve_api, "_require_case_contract", AsyncMock(return_value={"contract_id": 1}))
        monkeypatch.setattr(preserve_api, "_get_preservation_materials_service", lambda: service)
        monkeypatch.setattr(preserve_api, "_get_folder_binding_service", lambda: binding)

    @pytest.mark.asyncio
    async def test_multi_lane_agent_is_refused_before_generating(
        self, monkeypatch: pytest.MonkeyPatch, multi_session: str
    ) -> None:
        service = MagicMock()
        binding = _binding_service()
        self._patch(monkeypatch, service, binding)

        with pytest.raises(ConflictError) as exc_info:
            await preserve_api.download_full_package(_request(multi_session), case_id=2)

        assert exc_info.value.code == MULTI_LANE_WRITE_CODE
        assert exc_info.value.errors["endpoint"] == "documents.preservation.package"
        service.generate_full_package.assert_not_called()
        binding.extract_zip_for_contract.assert_not_called()

    @pytest.mark.asyncio
    async def test_lawyer_without_header_still_saves(self, monkeypatch: pytest.MonkeyPatch, multi_session: str) -> None:
        service = MagicMock()
        service.generate_full_package.return_value = (b"zip", "保全材料.zip")
        binding = _binding_service()
        self._patch(monkeypatch, service, binding)

        result = await preserve_api.download_full_package(_request(None), case_id=2)

        assert result["success"] is True
        assert result["filename"] == "保全材料.zip"
        binding.extract_zip_for_contract.assert_called_once()
