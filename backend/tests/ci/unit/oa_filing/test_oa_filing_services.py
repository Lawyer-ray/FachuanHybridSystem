"""
Tests for apps.oa_filing.services — OA立案服务
"""

from __future__ import annotations

import pytest


class TestOAFilingExceptions:
    """OA立案异常测试"""

    def test_oa_filing_error(self) -> None:
        from apps.oa_filing.services.exceptions import OAFilingError

        err = OAFilingError("测试错误")
        assert str(err) == "测试错误"
        assert err.message == "测试错误"

    def test_oa_filing_error_default(self) -> None:
        from apps.oa_filing.services.exceptions import OAFilingError

        err = OAFilingError()
        assert err.message == ""

    def test_script_execution_error(self) -> None:
        from apps.oa_filing.services.exceptions import OAFilingError, ScriptExecutionError

        err = ScriptExecutionError("脚本失败")
        assert isinstance(err, OAFilingError)
        assert isinstance(err, Exception)
        assert err.message == "脚本失败"

    def test_script_execution_error_default(self) -> None:
        from apps.oa_filing.services.exceptions import ScriptExecutionError

        err = ScriptExecutionError()
        assert err.message == "脚本执行失败"


class TestOAFilingModules:
    """OA立案模块可导入性测试"""

    def test_case_import_service_importable(self) -> None:
        from apps.oa_filing.services import case_import_service

        assert case_import_service is not None

    def test_script_executor_service_importable(self) -> None:
        from apps.oa_filing.services import script_executor_service

        assert script_executor_service is not None

    def test_import_session_service_importable(self) -> None:
        from apps.oa_filing.services import import_session_service

        assert import_session_service is not None

    def test_client_import_service_importable(self) -> None:
        from apps.oa_filing.services import client_import_service

        assert client_import_service is not None
