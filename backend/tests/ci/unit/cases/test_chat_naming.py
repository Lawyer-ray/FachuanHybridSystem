"""群聊名称构建与重建策略测试。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.cases.services.chat.naming import ChatNameBuilder
from apps.cases.services.chat.recreate_policy import ChatRecreatePolicy
from apps.core.exceptions import ValidationException


# ── ChatNameBuilder ────────────────────────────────────────────────────────

class TestChatNameBuilder:

    def _make_builder(self, chat_name: str = "【一审】测试案件") -> ChatNameBuilder:
        mock_config = MagicMock()
        mock_config.render_chat_name.return_value = chat_name
        return ChatNameBuilder(config_service=mock_config)

    def test_build_returns_chat_name(self) -> None:
        """正常构建群聊名称。"""
        builder = self._make_builder("【一审】张三诉李四")
        case = SimpleNamespace(name="张三诉李四", id=1, current_stage="first_instance",
                               case_type="civil")
        case.get_current_stage_display = lambda: "一审"
        case.get_case_type_display = lambda: "民事"
        result = builder.build(case=case)
        assert result == "【一审】张三诉李四"

    def test_build_empty_case_raises(self) -> None:
        """空案件对象抛出异常。"""
        builder = self._make_builder()
        with pytest.raises(ValidationException, match="案件对象不能为空"):
            builder.build(case=None)

    def test_build_no_name_raises(self) -> None:
        """案件名称为空抛出异常。"""
        builder = self._make_builder()
        case = SimpleNamespace(name=None, id=1)
        with pytest.raises(ValidationException, match="案件名称不能为空"):
            builder.build(case=case)

    def test_build_empty_name_raises(self) -> None:
        """案件名称为空字符串抛出异常。"""
        builder = self._make_builder()
        case = SimpleNamespace(name="", id=1)
        with pytest.raises(ValidationException, match="案件名称不能为空"):
            builder.build(case=case)

    def test_build_no_stage_uses_none(self) -> None:
        """案件无阶段时 stage 传 None。"""
        builder = self._make_builder()
        case = SimpleNamespace(name="测试案件", id=1, current_stage=None, case_type=None)
        builder.build(case=case)
        builder._config_service.render_chat_name.assert_called_once_with(
            case_name="测试案件", stage=None, case_type=None
        )

    def test_build_stage_display_fallback(self) -> None:
        """获取阶段显示名失败时回退到原始值。"""
        builder = self._make_builder()
        case = SimpleNamespace(name="测试案件", id=1, current_stage="xxx", case_type=None)
        case.get_current_stage_display = lambda: (_ for _ in ()).throw(ValueError("bad"))
        builder.build(case=case)
        call_kwargs = builder._config_service.render_chat_name.call_args
        assert call_kwargs[1]["stage"] == "xxx"

    def test_build_case_type_display_fallback(self) -> None:
        """获取类型显示名失败时回退到原始值。"""
        builder = self._make_builder()
        case = SimpleNamespace(name="测试案件", id=1, current_stage=None, case_type="civil")
        case.get_case_type_display = lambda: (_ for _ in ()).throw(AttributeError("bad"))
        builder.build(case=case)
        call_kwargs = builder._config_service.render_chat_name.call_args
        assert call_kwargs[1]["case_type"] == "civil"


# ── ChatRecreatePolicy ─────────────────────────────────────────────────────

class TestChatRecreatePolicy:

    def _make_result(self, error_code: str = "", message: str = "") -> SimpleNamespace:
        return SimpleNamespace(error_code=error_code, message=message)

    def test_no_error_returns_false(self) -> None:
        """无错误码时不重建。"""
        policy = ChatRecreatePolicy()
        assert policy.should_recreate(result=self._make_result("", "")) is False

    def test_feishu_not_found_code(self) -> None:
        """飞书群聊不存在错误码触发重建。"""
        policy = ChatRecreatePolicy()
        for code in ["230002", "230003", "230004", "99991663", "99991664"]:
            assert policy.should_recreate(result=self._make_result(code)) is True

    def test_dingtalk_not_found_code(self) -> None:
        """钉钉群聊不存在错误码触发重建。"""
        policy = ChatRecreatePolicy()
        for code in ["invalidParameter.chatId", "groupNotFound", "invalidChatId"]:
            assert policy.should_recreate(result=self._make_result(code)) is True

    def test_telegram_not_found_code(self) -> None:
        """Telegram 群组不存在错误码触发重建。"""
        policy = ChatRecreatePolicy()
        for code in ["400", "403"]:
            assert policy.should_recreate(result=self._make_result(code)) is True

    def test_message_keyword_chat_not_found(self) -> None:
        """消息中含"群聊不存在"触发重建。"""
        policy = ChatRecreatePolicy()
        assert policy.should_recreate(result=self._make_result("X", "群聊不存在")) is True

    def test_message_keyword_chat_dissolved(self) -> None:
        """消息中含"群聊已解散"触发重建。"""
        policy = ChatRecreatePolicy()
        assert policy.should_recreate(result=self._make_result("X", "群聊已解散")) is True

    def test_message_keyword_chat_not_found_english(self) -> None:
        """英文 "chat not found" 触发重建。"""
        policy = ChatRecreatePolicy()
        assert policy.should_recreate(result=self._make_result("X", "Error: chat not found")) is True

    def test_message_keyword_bot_not_in_chat(self) -> None:
        """机器人不在群聊中触发重建。"""
        policy = ChatRecreatePolicy()
        assert policy.should_recreate(result=self._make_result("X", "机器人不在群聊中")) is True

    def test_message_keyword_topic_not_found(self) -> None:
        """话题不存在触发重建。"""
        policy = ChatRecreatePolicy()
        assert policy.should_recreate(result=self._make_result("X", "topic not found")) is True

    def test_unrelated_error_returns_false(self) -> None:
        """无关错误码和消息不触发重建。"""
        policy = ChatRecreatePolicy()
        assert policy.should_recreate(result=self._make_result("SOME_OTHER", "network timeout")) is False

    def test_message_case_insensitive(self) -> None:
        """消息关键词匹配不区分大小写。"""
        policy = ChatRecreatePolicy()
        assert policy.should_recreate(result=self._make_result("X", "CHAT NOT FOUND")) is True
