"""ChatNameConfigService 单元测试。

覆盖模板/默认阶段读取的空值回退、渲染占位符替换与超长截断策略。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from apps.cases.services.chat.chat_name_config_service import ChatNameConfigService


def _make_service(
    template: str | None = None, default_stage: str | None = None
) -> tuple[ChatNameConfigService, MagicMock]:
    service = ChatNameConfigService()
    config = MagicMock()
    config.get_value.side_effect = lambda key, default=None: (
        template if key == ChatNameConfigService.CONFIG_KEY_TEMPLATE else default_stage
    )
    service._system_config_service = config
    return service, config


class TestLazyConfigService:
    def test_config_service_lazy_init(self) -> None:
        service = ChatNameConfigService()
        with patch("apps.cases.services.chat.chat_name_config_service._get_system_config_service") as mock_get:
            mock_get.return_value = "svc"
            assert service._config_service == "svc"
            # 复用已初始化实例，不再重复获取
            assert service._config_service == "svc"
            mock_get.assert_called_once()

    def test_wiring_helper_delegates_to_service_locator(self) -> None:
        from apps.cases.services.chat.chat_name_config_service import _get_system_config_service

        with patch("apps.cases.services.chat.wiring.ServiceLocator") as mock_sl:
            mock_sl.get_system_config_service.return_value = "located"
            assert _get_system_config_service() == "located"
            mock_sl.get_system_config_service.assert_called_once()


class TestGetTemplate:
    def test_configured_value_stripped(self) -> None:
        service, _ = _make_service(template="  【{stage}】{case_name}  ")
        assert service.get_template() == "【{stage}】{case_name}"

    def test_empty_falls_back_to_default(self) -> None:
        service, _ = _make_service(template="")
        assert service.get_template() == ChatNameConfigService.DEFAULT_TEMPLATE

    def test_whitespace_falls_back_to_default(self) -> None:
        service, _ = _make_service(template="   ")
        assert service.get_template() == ChatNameConfigService.DEFAULT_TEMPLATE

    def test_none_value_falls_back_to_default(self) -> None:
        service, _ = _make_service(template=None)
        assert service.get_template() == ChatNameConfigService.DEFAULT_TEMPLATE


class TestGetDefaultStage:
    def test_configured_value_stripped(self) -> None:
        service, _ = _make_service(default_stage=" 二审 ")
        assert service.get_default_stage() == "二审"

    def test_empty_falls_back(self) -> None:
        service, _ = _make_service(default_stage="")
        assert service.get_default_stage() == ChatNameConfigService.DEFAULT_STAGE

    def test_whitespace_falls_back(self) -> None:
        service, _ = _make_service(default_stage="  ")
        assert service.get_default_stage() == ChatNameConfigService.DEFAULT_STAGE


class TestGetMaxLength:
    def test_fixed_value(self) -> None:
        assert ChatNameConfigService().get_max_length() == 60


class TestRenderChatName:
    def test_basic_render(self) -> None:
        service, _ = _make_service()
        assert service.render_chat_name("张三诉李四合同纠纷案", "一审") == "【一审】张三诉李四合同纠纷案"

    def test_none_stage_uses_default(self) -> None:
        service, _ = _make_service()
        assert service.render_chat_name("案件", None) == "【待定】案件"

    def test_blank_stage_uses_default(self) -> None:
        service, _ = _make_service()
        assert service.render_chat_name("案件", "  ") == "【待定】案件"

    def test_empty_case_name_rendered_as_empty(self) -> None:
        service, _ = _make_service()
        assert service.render_chat_name("", "一审") == "【一审】"

    def test_case_type_placeholder(self) -> None:
        service, config = _make_service(template="【{stage}】{case_type}-{case_name}")
        config.get_value.side_effect = lambda key, default=None: (
            "【{stage}】{case_type}-{case_name}" if key == ChatNameConfigService.CONFIG_KEY_TEMPLATE else "待定"
        )
        assert service.render_chat_name("案件", "一审", case_type="民事") == "【一审】民事-案件"

    def test_truncation_with_stage_prefix(self) -> None:
        service, _ = _make_service()
        long_name = "超" * 100
        result = service.render_chat_name(long_name, "一审")
        assert len(result) == 60
        assert result.startswith("【一审】")
        assert result.endswith("...")

    def test_truncation_without_stage_prefix_format(self) -> None:
        """模板不以阶段前缀开头时整体截断加省略号。"""
        service, config = _make_service(template="{case_name}-{stage}")
        config.get_value.side_effect = lambda key, default=None: (
            "{case_name}-{stage}" if key == ChatNameConfigService.CONFIG_KEY_TEMPLATE else "待定"
        )
        result = service.render_chat_name("案" * 100, "一审")
        assert len(result) == 60
        assert result.endswith("...")


class TestRenderTemplate:
    def test_invalid_placeholder_kept_verbatim(self) -> None:
        service, _ = _make_service()
        result = service._render_template("【{stage}】{case_name}（{unknown}）", "一审", "案件", "民事")
        assert result == "【一审】案件（{unknown}）"

    def test_all_valid_placeholders_replaced(self) -> None:
        service, _ = _make_service()
        result = service._render_template("{stage}|{case_name}|{case_type}", "S", "N", "T")
        assert result == "S|N|T"


class TestTruncateChatName:
    def _service(self) -> ChatNameConfigService:
        service, _ = _make_service()
        return service

    def test_stage_prefix_truncated_body(self) -> None:
        service = self._service()
        result = service._truncate_chat_name(
            "【一审】" + "名" * 80, 60, "【{stage}】{case_name}", "一审", "名" * 80, ""
        )
        assert result.startswith("【一审】")
        assert result.endswith("...")
        assert len(result) == 60

    def test_stage_prefix_longer_than_max_truncates_whole(self) -> None:
        service = self._service()
        long_stage = "阶" * 70
        chat_name = f"【{long_stage}】案件"
        result = service._truncate_chat_name(chat_name, 60, "【{stage}】{case_name}", long_stage, "案件", "")
        # 阶段标识本身超限：整体截断（57 字符 + 3 省略号）
        assert len(result) == 60
        assert result.endswith("...")

    def test_non_prefix_format_truncated_whole(self) -> None:
        service = self._service()
        chat_name = "名" * 80
        result = service._truncate_chat_name(chat_name, 60, "{case_name}", "一审", chat_name, "")
        assert len(result) == 60
        assert result == "名" * 57 + "..."


class TestValidationConstants:
    def test_valid_placeholders(self) -> None:
        assert {"stage", "case_name", "case_type"} == ChatNameConfigService.VALID_PLACEHOLDERS

    def test_default_constants(self) -> None:
        assert ChatNameConfigService.DEFAULT_TEMPLATE == "【{stage}】{case_name}"
        assert ChatNameConfigService.DEFAULT_STAGE == "待定"
        assert ChatNameConfigService.DEFAULT_MAX_LENGTH == 60
