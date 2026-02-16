"""
SessionMessageService 单元测试
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.core.exceptions import NotFoundError
from apps.litigation_ai.services.session_message_service import SessionMessageService
from apps.litigation_ai.services.session_shared import MessageDTO


@pytest.mark.django_db
class TestSessionMessageService:
    """会话消息服务测试"""

    @pytest.fixture(autouse=True)
    def setup(self, test_lawyer, test_case):
        """每个测试方法前执行"""
        from apps.litigation_ai.services.session_lifecycle_service import SessionLifecycleService

        self.lawyer = test_lawyer
        self.case = test_case

        self.lifecycle_service = SessionLifecycleService()
        self.service = SessionMessageService()

    def test_add_message_success(self):
        """测试添加消息成功"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 执行测试
        message_dto = self.service.add_message(
            session_id=session_dto.session_id, role="user", content="测试消息", metadata={"key": "value"}
        )

        # 断言结果
        assert message_dto.session_id == session_dto.session_id
        assert message_dto.role == "user"
        assert message_dto.content == "测试消息"
        assert message_dto.metadata["key"] == "value"

    def test_add_message_session_not_found(self):
        """测试添加消息时会话不存在"""
        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.service.add_message(session_id="00000000-0000-0000-0000-000000000000", role="user", content="测试消息")

        assert "会话不存在" in exc_info.value.message
        assert exc_info.value.code == "SESSION_NOT_FOUND"

    def test_add_message_without_metadata(self):
        """测试添加消息不指定元数据"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 执行测试
        message_dto = self.service.add_message(session_id=session_dto.session_id, role="assistant", content="回复消息")

        # 断言结果
        assert message_dto.metadata == {}

    def test_get_messages_success(self):
        """测试获取消息列表成功"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 添加测试消息
        self.service.add_message(session_dto.session_id, "user", "消息1")
        self.service.add_message(session_dto.session_id, "assistant", "消息2")

        # 执行测试
        messages = self.service.get_messages(session_dto.session_id)

        # 断言结果
        assert len(messages) == 2
        assert messages[0].content == "消息1"
        assert messages[1].content == "消息2"

    def test_get_messages_session_not_found(self):
        """测试获取消息时会话不存在"""
        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.service.get_messages("00000000-0000-0000-0000-000000000000")

        assert "会话不存在" in exc_info.value.message

    def test_get_messages_with_limit(self):
        """测试获取消息列表限制数量"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 添加多条测试消息
        for i in range(10):
            self.service.add_message(session_dto.session_id, "user", f"消息{i}")

        # 执行测试
        messages = self.service.get_messages(session_dto.session_id, limit=5)

        # 断言结果
        assert len(messages) == 5

    def test_get_messages_with_offset(self):
        """测试获取消息列表偏移"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 添加测试消息
        self.service.add_message(session_dto.session_id, "user", "消息1")
        self.service.add_message(session_dto.session_id, "user", "消息2")
        self.service.add_message(session_dto.session_id, "user", "消息3")

        # 执行测试
        messages = self.service.get_messages(session_dto.session_id, limit=10, offset=1)

        # 断言结果
        assert len(messages) == 2
        assert messages[0].content == "消息2"

    def test_get_message_count_success(self):
        """测试获取消息数量成功"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 添加测试消息
        self.service.add_message(session_dto.session_id, "user", "消息1")
        self.service.add_message(session_dto.session_id, "assistant", "消息2")
        self.service.add_message(session_dto.session_id, "user", "消息3")

        # 执行测试
        count = self.service.get_message_count(session_dto.session_id)

        # 断言结果
        assert count == 3

    def test_get_message_count_session_not_found(self):
        """测试获取消息数量时会话不存在"""
        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.service.get_message_count("00000000-0000-0000-0000-000000000000")

        assert "会话不存在" in exc_info.value.message

    def test_get_message_count_empty(self):
        """测试获取消息数量为空"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 执行测试
        count = self.service.get_message_count(session_dto.session_id)

        # 断言结果
        assert count == 0

    def test_get_messages_batch_success(self):
        """测试批量获取消息成功"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 添加测试消息
        msg1 = self.service.add_message(session_dto.session_id, "user", "消息1")
        msg2 = self.service.add_message(session_dto.session_id, "user", "消息2")
        msg3 = self.service.add_message(session_dto.session_id, "user", "消息3")

        # 执行测试
        messages = self.service.get_messages_batch(session_dto.session_id, limit=10)

        # 断言结果
        assert len(messages) == 3

    def test_get_messages_batch_with_before_id(self):
        """测试批量获取消息指定 before_id"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 添加测试消息
        msg1 = self.service.add_message(session_dto.session_id, "user", "消息1")
        msg2 = self.service.add_message(session_dto.session_id, "user", "消息2")
        msg3 = self.service.add_message(session_dto.session_id, "user", "消息3")

        # 执行测试（获取 msg3 之前的消息）
        messages = self.service.get_messages_batch(session_dto.session_id, limit=10, before_id=msg3.id)

        # 断言结果
        assert len(messages) <= 2

    def test_get_messages_batch_session_not_found(self):
        """测试批量获取消息时会话不存在"""
        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.service.get_messages_batch("00000000-0000-0000-0000-000000000000")

        assert "会话不存在" in exc_info.value.message

    def test_save_conversation_summary_success(self):
        """测试保存对话摘要成功"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 执行测试
        self.service.save_conversation_summary(session_id=session_dto.session_id, summary="这是对话摘要")

        # 验证摘要已保存
        summary = self.service.get_conversation_summary(session_dto.session_id)
        assert summary == "这是对话摘要"

    def test_save_conversation_summary_session_not_found(self):
        """测试保存对话摘要时会话不存在"""
        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.service.save_conversation_summary(session_id="00000000-0000-0000-0000-000000000000", summary="摘要")

        assert "会话不存在" in exc_info.value.message

    def test_save_conversation_summary_update(self):
        """测试更新对话摘要"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 第一次保存
        self.service.save_conversation_summary(session_dto.session_id, "摘要1")

        # 第二次保存（更新）
        self.service.save_conversation_summary(session_dto.session_id, "摘要2")

        # 验证摘要已更新
        summary = self.service.get_conversation_summary(session_dto.session_id)
        assert summary == "摘要2"

    def test_get_conversation_summary_success(self):
        """测试获取对话摘要成功"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 保存摘要
        self.service.save_conversation_summary(session_dto.session_id, "测试摘要")

        # 执行测试
        summary = self.service.get_conversation_summary(session_dto.session_id)

        # 断言结果
        assert summary == "测试摘要"

    def test_get_conversation_summary_not_found(self):
        """测试获取对话摘要时会话不存在"""
        # 执行测试
        summary = self.service.get_conversation_summary("00000000-0000-0000-0000-000000000000")

        # 断言结果
        assert summary is None

    def test_get_conversation_summary_empty(self):
        """测试获取对话摘要为空"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 执行测试
        summary = self.service.get_conversation_summary(session_dto.session_id)

        # 断言结果
        assert summary is None

    def test_add_messages_batch_success(self):
        """测试批量添加消息成功"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 准备批量消息
        messages = [
            {"role": "user", "content": "消息1", "metadata": {}},
            {"role": "assistant", "content": "消息2", "metadata": {}},
            {"role": "user", "content": "消息3", "metadata": {"key": "value"}},
        ]

        # 执行测试
        created_messages = self.service.add_messages_batch(session_id=session_dto.session_id, messages=messages)

        # 断言结果
        assert len(created_messages) == 3
        assert created_messages[0].content == "消息1"
        assert created_messages[1].content == "消息2"
        assert created_messages[2].content == "消息3"
        assert created_messages[2].metadata["key"] == "value"

    def test_add_messages_batch_session_not_found(self):
        """测试批量添加消息时会话不存在"""
        messages = [
            {"role": "user", "content": "消息1"},
        ]

        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.service.add_messages_batch(session_id="00000000-0000-0000-0000-000000000000", messages=messages)

        assert "会话不存在" in exc_info.value.message

    def test_add_messages_batch_empty(self):
        """测试批量添加空消息列表"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 执行测试
        created_messages = self.service.add_messages_batch(session_id=session_dto.session_id, messages=[])

        # 断言结果
        assert len(created_messages) == 0


@pytest.mark.django_db
class TestSessionMessageServiceDTO:
    """会话消息服务 DTO 转换测试"""

    @pytest.fixture(autouse=True)
    def setup(self, test_lawyer, test_case):
        """每个测试方法前执行"""
        from apps.litigation_ai.services.session_lifecycle_service import SessionLifecycleService

        self.lawyer = test_lawyer
        self.case = test_case

        self.lifecycle_service = SessionLifecycleService()
        self.service = SessionMessageService()

    def test_to_message_dto(self):
        """测试 _to_message_dto 转换"""
        # 创建测试会话和消息
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)
        message_dto = self.service.add_message(
            session_id=session_dto.session_id, role="user", content="测试消息", metadata={"key": "value"}
        )

        # 断言结果
        assert isinstance(message_dto, MessageDTO)
        assert message_dto.session_id == session_dto.session_id
        assert message_dto.role == "user"
        assert message_dto.content == "测试消息"
        assert message_dto.metadata["key"] == "value"


@pytest.mark.django_db
class TestSessionMessageServiceEdgeCases:
    """会话消息服务边界情况测试"""

    @pytest.fixture(autouse=True)
    def setup(self, test_lawyer, test_case):
        """每个测试方法前执行"""
        from apps.litigation_ai.services.session_lifecycle_service import SessionLifecycleService

        self.lawyer = test_lawyer
        self.case = test_case

        self.lifecycle_service = SessionLifecycleService()
        self.service = SessionMessageService()

    def test_add_message_with_step_metadata(self):
        """测试添加消息包含 step 元数据"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 执行测试
        message_dto = self.service.add_message(
            session_id=session_dto.session_id, role="user", content="测试消息", metadata={"step": "evidence_collection"}
        )

        # 断言结果
        assert message_dto.metadata["step"] == "evidence_collection"

    def test_get_messages_order(self):
        """测试获取消息列表顺序"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 添加测试消息
        msg1 = self.service.add_message(session_dto.session_id, "user", "第一条")
        msg2 = self.service.add_message(session_dto.session_id, "user", "第二条")
        msg3 = self.service.add_message(session_dto.session_id, "user", "第三条")

        # 执行测试
        messages = self.service.get_messages(session_dto.session_id)

        # 断言结果（应该按时间升序）
        assert messages[0].content == "第一条"
        assert messages[1].content == "第二条"
        assert messages[2].content == "第三条"

    def test_get_messages_batch_reverse_order(self):
        """测试批量获取消息反转顺序"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 添加测试消息
        self.service.add_message(session_dto.session_id, "user", "第一条")
        self.service.add_message(session_dto.session_id, "user", "第二条")
        self.service.add_message(session_dto.session_id, "user", "第三条")

        # 执行测试
        messages = self.service.get_messages_batch(session_dto.session_id, limit=10)

        # 断言结果（应该按时间升序，因为代码中有 reverse）
        assert messages[0].content == "第一条"
        assert messages[1].content == "第二条"
        assert messages[2].content == "第三条"

    def test_save_conversation_summary_preserves_other_metadata(self):
        """测试保存对话摘要保留其他元数据"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 更新会话元数据
        self.lifecycle_service.update_session_status(
            session_id=session_dto.session_id, status="active", metadata_updates={"other_key": "other_value"}
        )

        # 保存摘要
        self.service.save_conversation_summary(session_dto.session_id, "摘要")

        # 获取会话
        session = self.lifecycle_service.get_session(session_dto.session_id)

        # 断言结果（其他元数据应该保留）
        assert session.metadata["conversation_summary"] == "摘要"
        assert session.metadata["other_key"] == "other_value"

    def test_add_messages_batch_with_default_role(self):
        """测试批量添加消息使用默认角色"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 准备批量消息（不指定 role）
        messages = [
            {"content": "消息1"},
            {"content": "消息2"},
        ]

        # 执行测试
        created_messages = self.service.add_messages_batch(session_id=session_dto.session_id, messages=messages)

        # 断言结果（应该使用默认角色 "user"）
        assert created_messages[0].role == "user"
        assert created_messages[1].role == "user"

    def test_message_count_after_batch_add(self):
        """测试批量添加消息后消息数量正确"""
        # 创建测试会话
        session_dto = self.lifecycle_service.create_session(case_id=self.case.id, user_id=self.lawyer.id)

        # 批量添加消息
        messages = [{"role": "user", "content": f"消息{i}"} for i in range(5)]
        self.service.add_messages_batch(session_dto.session_id, messages)

        # 执行测试
        count = self.service.get_message_count(session_dto.session_id)

        # 断言结果
        assert count == 5
