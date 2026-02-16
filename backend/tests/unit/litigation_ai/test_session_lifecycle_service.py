"""
SessionLifecycleService 单元测试
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from apps.litigation_ai.services.session_lifecycle_service import SessionLifecycleService
from apps.litigation_ai.services.session_shared import SessionDTO
from apps.core.exceptions import NotFoundError, ValidationException


@pytest.mark.django_db
class TestSessionLifecycleService:
    """会话生命周期服务测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = SessionLifecycleService()

    def test_create_session_success(self):
        """测试创建会话成功"""
        # 准备测试数据
        case_id = 1
        user_id = 100

        # 执行测试
        session_dto = self.service.create_session(case_id=case_id, user_id=user_id)

        # 断言结果
        assert session_dto.case_id == case_id
        assert session_dto.user_id == user_id
        assert session_dto.status == "active"
        assert session_dto.metadata == {}
        assert session_dto.session_id is not None

    def test_create_session_without_user(self):
        """测试创建会话不指定用户"""
        # 准备测试数据
        case_id = 1

        # 执行测试
        session_dto = self.service.create_session(case_id=case_id)

        # 断言结果
        assert session_dto.case_id == case_id
        assert session_dto.user_id is None
        assert session_dto.status == "active"

    def test_get_session_success(self):
        """测试获取会话成功"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 执行测试
        result = self.service.get_session(session_dto.session_id)

        # 断言结果
        assert result.session_id == session_dto.session_id
        assert result.case_id == session_dto.case_id
        assert result.user_id == session_dto.user_id

    def test_get_session_not_found(self):
        """测试获取不存在的会话"""
        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.service.get_session("non-existent-session-id")

        assert "会话不存在" in exc_info.value.message
        assert exc_info.value.code == "SESSION_NOT_FOUND"

    def test_update_session_status_success(self):
        """测试更新会话状态成功"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 执行测试
        updated_dto = self.service.update_session_status(
            session_id=session_dto.session_id,
            status="completed",
            metadata_updates={"result": "success"}
        )

        # 断言结果
        assert updated_dto.status == "completed"
        assert updated_dto.metadata["result"] == "success"

    def test_update_session_status_invalid_status(self):
        """测试更新会话状态为无效状态"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.update_session_status(
                session_id=session_dto.session_id,
                status="invalid_status"
            )

        assert "无效的状态" in exc_info.value.message
        assert exc_info.value.code == "INVALID_STATUS"

    def test_update_session_status_not_found(self):
        """测试更新不存在的会话状态"""
        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.service.update_session_status(
                session_id="non-existent-session-id",
                status="completed"
            )

        assert "会话不存在" in exc_info.value.message

    def test_list_sessions_all(self):
        """测试列出所有会话"""
        # 创建测试会话
        self.service.create_session(case_id=1, user_id=100)
        self.service.create_session(case_id=2, user_id=100)

        # 执行测试
        result = self.service.list_sessions()

        # 断言结果
        assert result["total"] == 2
        assert len(result["sessions"]) == 2

    def test_list_sessions_filter_by_user(self):
        """测试按用户过滤会话"""
        # 创建测试会话
        self.service.create_session(case_id=1, user_id=100)
        self.service.create_session(case_id=2, user_id=200)

        # 执行测试
        result = self.service.list_sessions(user_id=100)

        # 断言结果
        assert result["total"] == 1
        assert result["sessions"][0]["case_id"] == 1

    def test_list_sessions_filter_by_case(self):
        """测试按案件过滤会话"""
        # 创建测试会话
        self.service.create_session(case_id=1, user_id=100)
        self.service.create_session(case_id=1, user_id=200)
        self.service.create_session(case_id=2, user_id=100)

        # 执行测试
        result = self.service.list_sessions(case_id=1)

        # 断言结果
        assert result["total"] == 2

    def test_list_sessions_filter_by_status(self):
        """测试按状态过滤会话"""
        # 创建测试会话
        session1 = self.service.create_session(case_id=1, user_id=100)
        session2 = self.service.create_session(case_id=2, user_id=100)

        # 更新一个会话的状态
        self.service.update_session_status(session1.session_id, "completed")

        # 执行测试
        result = self.service.list_sessions(status="active")

        # 断言结果
        assert result["total"] == 1
        assert result["sessions"][0]["session_id"] == session2.session_id

    def test_list_sessions_with_pagination(self):
        """测试会话列表分页"""
        # 创建多个测试会话
        for i in range(25):
            self.service.create_session(case_id=i, user_id=100)

        # 执行测试（第一页）
        result_page1 = self.service.list_sessions(limit=10, offset=0)

        # 断言结果
        assert result_page1["total"] == 25
        assert len(result_page1["sessions"]) == 10
        assert result_page1["limit"] == 10
        assert result_page1["offset"] == 0

        # 执行测试（第二页）
        result_page2 = self.service.list_sessions(limit=10, offset=10)

        # 断言结果
        assert result_page2["total"] == 25
        assert len(result_page2["sessions"]) == 10
        assert result_page2["offset"] == 10

    def test_delete_session_success(self):
        """测试删除会话成功"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 创建 Mock 用户
        user = Mock()
        user.id = 100

        # 执行测试
        self.service.delete_session(session_dto.session_id, user=user)

        # 验证会话已删除
        with pytest.raises(NotFoundError):
            self.service.get_session(session_dto.session_id)

    def test_delete_session_not_found(self):
        """测试删除不存在的会话"""
        # 创建 Mock 用户
        user = Mock()
        user.id = 100

        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.service.delete_session("non-existent-session-id", user=user)

        assert "会话不存在" in exc_info.value.message

    def test_delete_session_permission_denied(self):
        """测试删除会话权限不足"""
        from apps.core.exceptions import PermissionDenied

        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 创建 Mock 用户（不同的用户）
        user = Mock()
        user.id = 200

        # 断言抛出异常
        with pytest.raises(PermissionDenied) as exc_info:
            self.service.delete_session(session_dto.session_id, user=user)

        assert "无权限删除此会话" in exc_info.value.message

    def test_delete_session_without_user(self):
        """测试删除会话不检查权限"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 执行测试（不传入用户）
        self.service.delete_session(session_dto.session_id)

        # 验证会话已删除
        with pytest.raises(NotFoundError):
            self.service.get_session(session_dto.session_id)

    @patch('apps.litigation_ai.services.session_lifecycle_service.get_case_service')
    @patch('apps.litigation_ai.services.session_lifecycle_service.get_court_pleading_signals_service')
    def test_get_recommended_document_types_plaintiff(self, mock_signals_service, mock_case_service):
        """测试获取推荐文书类型（原告方）"""
        from apps.core.enums import LegalStatus
        from apps.litigation_ai.models.choices import DocumentType

        # 配置 Mock
        mock_case = Mock()
        mock_case.id = 1
        mock_case_service.return_value.get_case_internal.return_value = mock_case

        mock_party = Mock()
        mock_party.legal_status = LegalStatus.PLAINTIFF
        mock_case_service.return_value.get_case_parties_internal.return_value = [mock_party]

        mock_signals = Mock()
        mock_signals.has_counterclaim = False
        mock_signals_service.return_value.get_signals_internal.return_value = mock_signals

        # 执行测试
        result = self.service.get_recommended_document_types(case_id=1)

        # 断言结果
        assert DocumentType.COMPLAINT in result
        assert DocumentType.COUNTERCLAIM_DEFENSE not in result

    @patch('apps.litigation_ai.services.session_lifecycle_service.get_case_service')
    @patch('apps.litigation_ai.services.session_lifecycle_service.get_court_pleading_signals_service')
    def test_get_recommended_document_types_defendant(self, mock_signals_service, mock_case_service):
        """测试获取推荐文书类型（被告方）"""
        from apps.core.enums import LegalStatus
        from apps.litigation_ai.models.choices import DocumentType

        # 配置 Mock
        mock_case = Mock()
        mock_case.id = 1
        mock_case_service.return_value.get_case_internal.return_value = mock_case

        mock_party = Mock()
        mock_party.legal_status = LegalStatus.DEFENDANT
        mock_case_service.return_value.get_case_parties_internal.return_value = [mock_party]

        mock_signals = Mock()
        mock_signals.has_counterclaim = False
        mock_signals_service.return_value.get_signals_internal.return_value = mock_signals

        # 执行测试
        result = self.service.get_recommended_document_types(case_id=1)

        # 断言结果
        assert DocumentType.DEFENSE in result
        assert DocumentType.COUNTERCLAIM in result

    @patch('apps.litigation_ai.services.session_lifecycle_service.get_case_service')
    def test_get_recommended_document_types_case_not_found(self, mock_case_service):
        """测试获取推荐文书类型时案件不存在"""
        # 配置 Mock
        mock_case_service.return_value.get_case_internal.return_value = None

        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.service.get_recommended_document_types(case_id=999)

        assert "案件不存在" in exc_info.value.message
        assert exc_info.value.code == "CASE_NOT_FOUND"


@pytest.mark.django_db
class TestSessionLifecycleServiceDTO:
    """会话生命周期服务 DTO 转换测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = SessionLifecycleService()

    def test_to_session_dto(self):
        """测试 _to_session_dto 转换"""
        from apps.litigation_ai.models import LitigationSession

        # 创建测试会话
        session = LitigationSession.objects.create(
            case_id=1,
            user_id=100,
            status="active",
            metadata={"key": "value"}
        )

        # 执行转换
        dto = SessionLifecycleService._to_session_dto(session)

        # 断言结果
        assert isinstance(dto, SessionDTO)
        assert dto.id == session.id
        assert dto.session_id == str(session.session_id)
        assert dto.case_id == session.case_id
        assert dto.user_id == session.user_id
        assert dto.status == session.status
        assert dto.metadata == session.metadata

    def test_to_session_dto_with_case(self):
        """测试 _to_session_dto 转换（包含案件信息）"""
        from apps.litigation_ai.models import LitigationSession
        from apps.cases.models import Case

        # 创建测试案件和会话
        case = Case.objects.create(name="测试案件", is_archived=False)
        session = LitigationSession.objects.create(
            case_id=case.id,
            user_id=100,
            status="active",
            metadata={}
        )

        # 预加载案件信息
        session = LitigationSession.objects.select_related('case').get(id=session.id)

        # 执行转换
        dto = SessionLifecycleService._to_session_dto(session)

        # 断言结果
        assert dto.case_name == "测试案件"


@pytest.mark.django_db
class TestSessionLifecycleServiceEdgeCases:
    """会话生命周期服务边界情况测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = SessionLifecycleService()

    def test_update_session_metadata_merge(self):
        """测试更新会话元数据合并"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 第一次更新
        self.service.update_session_status(
            session_id=session_dto.session_id,
            status="active",
            metadata_updates={"key1": "value1"}
        )

        # 第二次更新
        updated_dto = self.service.update_session_status(
            session_id=session_dto.session_id,
            status="active",
            metadata_updates={"key2": "value2"}
        )

        # 断言结果（元数据应该合并）
        assert updated_dto.metadata["key1"] == "value1"
        assert updated_dto.metadata["key2"] == "value2"

    def test_list_sessions_empty_result(self):
        """测试列出会话为空"""
        # 执行测试
        result = self.service.list_sessions()

        # 断言结果
        assert result["total"] == 0
        assert len(result["sessions"]) == 0

    def test_list_sessions_with_message_count(self):
        """测试列出会话包含消息数量"""
        # 创建测试会话
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 执行测试
        result = self.service.list_sessions()

        # 断言结果
        assert "message_count" in result["sessions"][0]
        assert result["sessions"][0]["message_count"] >= 0

    def test_create_session_with_metadata(self):
        """测试创建会话时元数据初始化"""
        # 执行测试
        session_dto = self.service.create_session(case_id=1, user_id=100)

        # 断言结果
        assert isinstance(session_dto.metadata, dict)
        assert len(session_dto.metadata) == 0
