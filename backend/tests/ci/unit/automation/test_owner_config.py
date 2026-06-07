"""群主配置管理器和 Mac 打印执行器测试。"""

from __future__ import annotations

import re

from apps.automation.services.chat.owner_config_manager import OwnerConfigManager
from apps.batch_printing.services.execution.mac_print_executor_service import MacPrintExecutorService


class TestOwnerConfigManager:
    """OwnerConfigManager 测试。"""

    def test_open_id_pattern(self) -> None:
        """飞书 open_id 格式验证。"""
        assert OwnerConfigManager.OPEN_ID_PATTERN.match("ou_1234567890abcdef1234567890abcdef") is not None
        assert OwnerConfigManager.OPEN_ID_PATTERN.match("ou_invalid") is None
        assert OwnerConfigManager.OPEN_ID_PATTERN.match("") is None
        assert OwnerConfigManager.OPEN_ID_PATTERN.match("on_1234567890abcdef1234567890abcdef") is None

    def test_union_id_pattern(self) -> None:
        """飞书 union_id 格式验证。"""
        assert OwnerConfigManager.UNION_ID_PATTERN.match("on_1234567890abcdef1234567890abcdef") is not None
        assert OwnerConfigManager.UNION_ID_PATTERN.match("on_invalid") is None
        assert OwnerConfigManager.UNION_ID_PATTERN.match("") is None
        assert OwnerConfigManager.UNION_ID_PATTERN.match("ou_1234567890abcdef1234567890abcdef") is None

    def test_open_id_pattern_length(self) -> None:
        """open_id 必须是 32 位十六进制。"""
        # 31 位不匹配
        assert OwnerConfigManager.OPEN_ID_PATTERN.match("ou_" + "a" * 31) is None
        # 32 位匹配
        assert OwnerConfigManager.OPEN_ID_PATTERN.match("ou_" + "a" * 32) is not None
        # 33 位不匹配
        assert OwnerConfigManager.OPEN_ID_PATTERN.match("ou_" + "a" * 33) is None

    def test_patterns_are_compiled(self) -> None:
        """正则模式已编译。"""
        assert isinstance(OwnerConfigManager.OPEN_ID_PATTERN, type(re.compile("")))
        assert isinstance(OwnerConfigManager.UNION_ID_PATTERN, type(re.compile("")))


class TestMacPrintExecutorService:
    """MacPrintExecutorService 测试。"""

    def test_print_pdf_file_not_exists(self) -> None:
        """文件不存在抛出异常。"""
        from pathlib import Path

        service = MacPrintExecutorService()
        from apps.core.exceptions import ValidationException

        try:
            service.print_pdf(printer_name="HP", options={}, pdf_path=Path("/nonexistent/file.pdf"))
            assert False, "应抛出 ValidationException"
        except ValidationException as e:
            assert "不存在" in str(e)

    def test_print_pdf_empty_printer(self) -> None:
        """空打印机名抛出异常。"""
        from pathlib import Path
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"fake pdf")
            f.flush()

            service = MacPrintExecutorService()
            from apps.core.exceptions import ValidationException

            try:
                service.print_pdf(printer_name="", options={}, pdf_path=Path(f.name))
                assert False, "应抛出 ValidationException"
            except ValidationException as e:
                assert "未指定打印机" in str(e)
