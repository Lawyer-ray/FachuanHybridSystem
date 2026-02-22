"""
LitigationConversationSessionService 单元测试（聚合服务）
"""

from unittest.mock import Mock, patch

import pytest

from apps.core.exceptions import NotFoundError
from apps.litigation_ai.services.conversation_session_service import LitigationConversationSessionService


@pytest.mark.django_db
class TestLitigationConversationSessionService:
    """诉讼AI对话会话服务测试（聚合服务）"""

    def setup_method(self):
        """每个测试方法前执行"""
        from apps.cases.models import Case
        from apps.organization.models import Lawyer
        Lawyer.objects.get_or_create(id=100, defaults={"username": "test_user_100", "password": "!"})
        Case.objects.get_or_create(id=1, defaults={"name": "测试案件"})
        Case.objects.get_or_create(id=2, defaults={"name": "测试案件2"})
        self.service = LitigationConversationSessionService()

    def test_service_initialization(self):
        """测试服务初始化"""
        # 断言内部服务已初始化
        assert self.service._lifecycle is not None
        assert self.service._messages is not None

    def test_create_session_delegates_to_lifecycle(self):
        """测试创建会话委托给生命周期服务"""
        # 执行测试
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 断言结果
        assert session_dto.case_id == 1
        assert session_dto.user_id == 100

    def test_get_session_delegates_to_lifecycle(self):
        """测试获取会话委托给生命周期服务"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 执行测试
        result = self.service.get_session(session_dto.session_id)

        # 断言结果
        assert result.session_id == session_dto.session_id

    def test_update_session_status_delegates_to_lifecycle(self):
        """测试更新会话状态委托给生命周期服务"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 执行测试
        updated_dto = self.service.update_session_status(session_id=session_dto.session_id, status="completed")

        # 断言结果
        assert updated_dto.status == "completed"

    def test_list_sessions_delegates_to_lifecycle(self):
        """测试列出会话委托给生命周期服务"""
        # 创建测试会话
        self.service.create_session(case_id=1, user_id=100)

        # 执行测试
        result = self.service.list_sessions()

        # 断言结果
        assert result["total"] >= 1

    def test_delete_session_delegates_to_lifecycle(self):
        """测试删除会话委托给生命周期服务"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 执行测试
        self.service.delete_session(session_dto.session_id)

        # 验证会话已删除
        with pytest.raises(NotFoundError):
            self.service.get_session(session_dto.session_id)

    def test_add_message_delegates_to_messages(self):
        """测试添加消息委托给消息服务"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 执行测试
        message_dto = self.service.add_message(session_id=session_dto.session_id, role="user", content="测试消息")

        # 断言结果
        assert message_dto.content == "测试消息"

    def test_get_messages_delegates_to_messages(self):
        """测试获取消息委托给消息服务"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)
        self.service.add_message(session_dto.session_id, "user", "消息1")

        # 执行测试
        messages = self.service.get_messages(session_dto.session_id)

        # 断言结果
        assert len(messages) >= 1

    def test_get_message_count_delegates_to_messages(self):
        """测试获取消息数量委托给消息服务"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)
        self.service.add_message(session_dto.session_id, "user", "消息1")

        # 执行测试
        count = self.service.get_message_count(session_dto.session_id)

        # 断言结果
        assert count >= 1

    def test_save_conversation_summary_delegates_to_messages(self):
        """测试保存对话摘要委托给消息服务"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 执行测试
        self.service.save_conversation_summary(session_dto.session_id, "摘要")

        # 验证摘要已保存
        summary = self.service.get_conversation_summary(session_dto.session_id)
        assert summary == "摘要"

    def test_get_conversation_summary_delegates_to_messages(self):
        """测试获取对话摘要委托给消息服务"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)
        self.service.save_conversation_summary(session_dto.session_id, "测试摘要")

        # 执行测试
        summary = self.service.get_conversation_summary(session_dto.session_id)

        # 断言结果
        assert summary == "测试摘要"

    def test_add_messages_batch_delegates_to_messages(self):
        """测试批量添加消息委托给消息服务"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 准备批量消息
        messages = [
            {"role": "user", "content": "消息1"},
            {"role": "assistant", "content": "消息2"},
        ]

        # 执行测试
        created_messages = self.service.add_messages_batch(session_id=session_dto.session_id, messages=messages)

        # 断言结果
        assert len(created_messages) == 2

    def test_get_messages_batch_delegates_to_messages(self):
        """测试批量获取消息委托给消息服务"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)
        self.service.add_message(session_dto.session_id, "user", "消息1")

        # 执行测试
        messages = self.service.get_messages_batch(session_dto.session_id)

        # 断言结果
        assert len(messages) >= 1

    @patch("apps.litigation_ai.services.session_lifecycle_service.get_case_service")
    @patch("apps.litigation_ai.services.session_lifecycle_service.get_court_pleading_signals_service")
    def test_get_recommended_document_types_delegates_to_lifecycle(self, mock_signals_service, mock_case_service):
        """测试获取推荐文书类型委托给生命周期服务"""
        from apps.core.enums import LegalStatus
        from apps.litigation_ai.models.choices import DocumentType

        # 配置 Mock
        mock_case = Mock()
        mock_case.id = 1

        mock_party = Mock()
        mock_party.legal_status = LegalStatus.PLAINTIFF

        mock_signals = Mock()
        mock_signals.has_counterclaim = False

        # 直接 mock 已实例化的 case_service 和 signals service
        self.service._lifecycle.case_service = Mock()
        self.service._lifecycle.case_service.get_case_internal.return_value = mock_case
        self.service._lifecycle.case_service.get_case_parties_internal.return_value = [mock_party]

        mock_signals_instance = Mock()
        mock_signals_instance.get_signals_internal.return_value = mock_signals
        mock_signals_service.return_value = mock_signals_instance

        # 执行测试
        result = self.service.get_recommended_document_types(case_id=1)

        # 断言结果
        assert DocumentType.COMPLAINT in result


@pytest.mark.django_db
class TestLitigationConversationSessionServiceProperties:
    """诉讼AI对话会话服务属性测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        from apps.cases.models import Case
        from apps.organization.models import Lawyer
        Lawyer.objects.get_or_create(id=100, defaults={"username": "test_user_100", "password": "!"})
        Case.objects.get_or_create(id=1, defaults={"name": "测试案件"})
        Case.objects.get_or_create(id=2, defaults={"name": "测试案件2"})
        self.service = LitigationConversationSessionService()

    def test_case_service_property(self):
        """测试 case_service 属性"""
        # 执行测试
        case_service = self.service.case_service

        # 断言结果
        assert case_service is not None

    def test_conversation_history_service_property(self):
        """测试 conversation_history_service 属性"""
        # 执行测试
        history_service = self.service.conversation_history_service

        # 断言结果
        assert history_service is not None

    def test_session_repo_property(self):
        """测试 session_repo 属性"""
        # 执行测试
        session_repo = self.service.session_repo

        # 断言结果
        assert session_repo is not None


@pytest.mark.django_db
class TestLitigationConversationSessionServiceBackwardCompatibility:
    """诉讼AI对话会话服务向后兼容性测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        from apps.cases.models import Case
        from apps.organization.models import Lawyer
        Lawyer.objects.get_or_create(id=100, defaults={"username": "test_user_100", "password": "!"})
        Case.objects.get_or_create(id=1, defaults={"name": "测试案件"})
        Case.objects.get_or_create(id=2, defaults={"name": "测试案件2"})
        self.service = LitigationConversationSessionService()

    def test_to_session_dto_backward_compatibility(self):
        """测试 _to_session_dto 向后兼容"""
        from apps.litigation_ai.models import LitigationSession

        # 创建测试会话
        session = LitigationSession.objects.create(case_id=1, user_id=100, status="active", metadata={})

        # 执行测试
        dto = self.service._to_session_dto(session)

        # 断言结果
        assert dto.session_id == str(session.session_id)

    def test_to_message_dto_backward_compatibility(self):
        """测试 _to_message_dto 向后兼容"""
        # 创建测试会话和消息
        session_dto = self.service.create_session(case_id=1, user_id=100)
        message_dto = self.service.add_message(session_id=session_dto.session_id, role="user", content="测试消息")

        # 从数据库获取消息对象
        from apps.core.models import ConversationHistory

        message = ConversationHistory.objects.get(id=message_dto.id)

        # 执行测试
        dto = self.service._to_message_dto(message)

        # 断言结果
        assert dto.content == "测试消息"


@pytest.mark.django_db
class TestLitigationConversationSessionServiceIntegration:
    """诉讼AI对话会话服务集成测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        from apps.cases.models import Case
        from apps.organization.models import Lawyer
        Lawyer.objects.get_or_create(id=100, defaults={"username": "test_user_100", "password": "!"})
        Lawyer.objects.get_or_create(id=200, defaults={"username": "test_user_200", "password": "!"})
        Case.objects.get_or_create(id=1, defaults={"name": "测试案件"})
        Case.objects.get_or_create(id=2, defaults={"name": "测试案件2"})
        self.service = LitigationConversationSessionService()

    def test_full_conversation_flow(self):
        """测试完整对话流程"""
        # 1. 创建会话
        session_dto = self.service.create_session(case_id=1, user_id=100)
        assert session_dto.status == "active"

        # 2. 添加消息
        msg1 = self.service.add_message(session_dto.session_id, "user", "用户问题")
        msg2 = self.service.add_message(session_dto.session_id, "assistant", "AI回复")
        assert msg1.role == "user"
        assert msg2.role == "assistant"

        # 3. 获取消息列表
        messages = self.service.get_messages(session_dto.session_id)
        assert len(messages) == 2

        # 4. 获取消息数量
        count = self.service.get_message_count(session_dto.session_id)
        assert count == 2

        # 5. 保存对话摘要
        self.service.save_conversation_summary(session_dto.session_id, "对话摘要")

        # 6. 获取对话摘要
        summary = self.service.get_conversation_summary(session_dto.session_id)
        assert summary == "对话摘要"

        # 7. 更新会话状态
        updated_dto = self.service.update_session_status(session_dto.session_id, "completed")
        assert updated_dto.status == "completed"

        # 8. 删除会话
        self.service.delete_session(session_dto.session_id)

        # 9. 验证会话已删除
        with pytest.raises(NotFoundError):
            self.service.get_session(session_dto.session_id)

    def test_multiple_sessions_isolation(self):
        """测试多个会话隔离"""
        # 创建两个会话
        session1 = self.service.create_session(case_id=1, user_id=100)
        session2 = self.service.create_session(case_id=2, user_id=200)

        # 给每个会话添加消息
        self.service.add_message(session1.session_id, "user", "会话1消息")
        self.service.add_message(session2.session_id, "user", "会话2消息")

        # 验证消息隔离
        messages1 = self.service.get_messages(session1.session_id)
        messages2 = self.service.get_messages(session2.session_id)

        assert len(messages1) == 1
        assert len(messages2) == 1
        assert messages1[0].content == "会话1消息"
        assert messages2[0].content == "会话2消息"

    def test_batch_operations(self):
        """测试批量操作"""
        # 创建会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 批量添加消息
        messages = [{"role": "user", "content": f"消息{i}"} for i in range(5)]
        created_messages = self.service.add_messages_batch(session_id=session_dto.session_id, messages=messages)

        # 验证批量添加成功
        assert len(created_messages) == 5

        # 批量获取消息
        batch_messages = self.service.get_messages_batch(session_dto.session_id, limit=10)
        assert len(batch_messages) == 5

        # 验证消息数量
        count = self.service.get_message_count(session_dto.session_id)
        assert count == 5

    def test_session_lifecycle_with_metadata(self):
        """测试会话生命周期包含元数据"""
        # 创建会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 更新元数据
        updated_dto = self.service.update_session_status(
            session_id=session_dto.session_id,
            status="active",
            metadata_updates={"step": "evidence_collection", "progress": 50},
        )

        # 验证元数据
        assert updated_dto.metadata["step"] == "evidence_collection"
        assert updated_dto.metadata["progress"] == 50

        # 保存对话摘要（不应影响其他元数据）
        self.service.save_conversation_summary(session_dto.session_id, "摘要")

        # 获取会话验证元数据完整性
        session = self.service.get_session(session_dto.session_id)
        assert session.metadata["step"] == "evidence_collection"
        assert session.metadata["progress"] == 50
        assert session.metadata["conversation_summary"] == "摘要"
