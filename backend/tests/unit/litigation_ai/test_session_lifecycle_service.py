"""
SessionLifecycleService 单元测试
"""

import uuid
from unittest.mock import Mock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.litigation_ai.services.session_lifecycle_service import SessionLifecycleService
from apps.litigation_ai.services.session_shared import SessionDTO

_NONEXISTENT_UUID = str(uuid.uuid4())


def _make_case(name: str = "测试案件") -> "Case":  # type: ignore[name-defined] # noqa: F821
    from apps.cases.models import Case
    return Case.objects.create(name=name, is_archived=False)


def _make_lawyer(username: str = "test_lawyer") -> "Lawyer":  # type: ignore[name-defined] # noqa: F821
    from apps.organization.models import Lawyer
    return Lawyer.objects.create_user(
        username=username, password="testpass", real_name="测试律师", is_active=True
    )


@pytest.mark.django_db
class TestSessionLifecycleService:
    """会话生命周期服务测试"""

    def setup_method(self):
        self.service = SessionLifecycleService()
        self.case = _make_case()
        self.lawyer = _make_lawyer()
        self.case_id = self.case.id
        self.user_id = self.lawyer.id

    def test_create_session_success(self):
        """测试创建会话成功"""
        session_dto = self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        assert session_dto.case_id == self.case_id
        assert session_dto.user_id == self.user_id
        assert session_dto.status == "active"
        assert session_dto.metadata == {}
        assert session_dto.session_id is not None

    def test_create_session_without_user(self):
        """测试创建会话不指定用户"""
        session_dto = self.service.create_session(case_id=self.case_id)

        assert session_dto.case_id == self.case_id
        assert session_dto.user_id is None
        assert session_dto.status == "active"

    def test_get_session_success(self):
        """测试获取会话成功"""
        session_dto = self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        result = self.service.get_session(session_dto.session_id)

        assert result.session_id == session_dto.session_id
        assert result.case_id == session_dto.case_id
        assert result.user_id == session_dto.user_id

    def test_get_session_not_found(self):
        """测试获取不存在的会话"""
        with pytest.raises(NotFoundError) as exc_info:
            self.service.get_session(_NONEXISTENT_UUID)

        assert "会话不存在" in exc_info.value.message  # type: ignore[operator]
        assert exc_info.value.code == "SESSION_NOT_FOUND"

    def test_update_session_status_success(self):
        """测试更新会话状态成功"""
        session_dto = self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        updated_dto = self.service.update_session_status(
            session_id=session_dto.session_id, status="completed", metadata_updates={"result": "success"}
        )

        assert updated_dto.status == "completed"
        assert updated_dto.metadata["result"] == "success"

    def test_update_session_status_invalid_status(self):
        """测试更新会话状态为无效状态"""
        session_dto = self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        with pytest.raises(ValidationException) as exc_info:
            self.service.update_session_status(session_id=session_dto.session_id, status="invalid_status")

        assert "无效的状态" in exc_info.value.message  # type: ignore[operator]
        assert exc_info.value.code == "INVALID_STATUS"

    def test_update_session_status_not_found(self):
        """测试更新不存在的会话状态"""
        with pytest.raises(NotFoundError) as exc_info:
            self.service.update_session_status(session_id=_NONEXISTENT_UUID, status="completed")

        assert "会话不存在" in exc_info.value.message  # type: ignore[operator]

    def test_list_sessions_all(self):
        """测试列出所有会话"""
        self.service.create_session(case_id=self.case_id, user_id=self.user_id)
        self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        result = self.service.list_sessions()

        assert result["total"] == 2
        assert len(result["sessions"]) == 2

    def test_list_sessions_filter_by_user(self):
        """测试按用户过滤会话"""
        lawyer2 = _make_lawyer("test_lawyer2")
        self.service.create_session(case_id=self.case_id, user_id=self.user_id)
        self.service.create_session(case_id=self.case_id, user_id=lawyer2.id)

        result = self.service.list_sessions(user_id=self.user_id)

        assert result["total"] == 1
        assert result["sessions"][0]["case_id"] == self.case_id

    def test_list_sessions_filter_by_case(self):
        """测试按案件过滤会话"""
        case2 = _make_case("案件2")
        lawyer2 = _make_lawyer("test_lawyer2")
        self.service.create_session(case_id=self.case_id, user_id=self.user_id)
        self.service.create_session(case_id=self.case_id, user_id=lawyer2.id)
        self.service.create_session(case_id=case2.id, user_id=self.user_id)

        result = self.service.list_sessions(case_id=self.case_id)

        assert result["total"] == 2

    def test_list_sessions_filter_by_status(self):
        """测试按状态过滤会话"""
        session1 = self.service.create_session(case_id=self.case_id, user_id=self.user_id)
        session2 = self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        self.service.update_session_status(session1.session_id, "completed")

        result = self.service.list_sessions(status="active")

        assert result["total"] == 1
        assert result["sessions"][0]["session_id"] == session2.session_id

    def test_list_sessions_with_pagination(self):
        """测试会话列表分页"""
        for _ in range(25):
            self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        result_page1 = self.service.list_sessions(limit=10, offset=0)

        assert result_page1["total"] == 25
        assert len(result_page1["sessions"]) == 10
        assert result_page1["limit"] == 10
        assert result_page1["offset"] == 0

        result_page2 = self.service.list_sessions(limit=10, offset=10)

        assert result_page2["total"] == 25
        assert len(result_page2["sessions"]) == 10
        assert result_page2["offset"] == 10

    def test_delete_session_success(self):
        """测试删除会话成功"""
        session_dto = self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        user = Mock()
        user.id = self.user_id

        self.service.delete_session(session_dto.session_id, user=user)

        with pytest.raises(NotFoundError):
            self.service.get_session(session_dto.session_id)

    def test_delete_session_not_found(self):
        """测试删除不存在的会话"""
        user = Mock()
        user.id = self.user_id

        with pytest.raises(NotFoundError) as exc_info:
            self.service.delete_session(_NONEXISTENT_UUID, user=user)

        assert "会话不存在" in exc_info.value.message  # type: ignore[operator]

    def test_delete_session_permission_denied(self):
        """测试删除会话权限不足"""
        from apps.core.exceptions import PermissionDenied

        session_dto = self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        user = Mock()
        user.id = self.user_id + 9999

        with pytest.raises(PermissionDenied) as exc_info:
            self.service.delete_session(session_dto.session_id, user=user)

        assert "无权限删除此会话" in exc_info.value.message  # type: ignore[operator]

    def test_delete_session_without_user(self):
        """测试删除会话不检查权限"""
        session_dto = self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        self.service.delete_session(session_dto.session_id)

        with pytest.raises(NotFoundError):
            self.service.get_session(session_dto.session_id)

    @patch("apps.litigation_ai.services.wiring.get_court_pleading_signals_service")
    def test_get_recommended_document_types_plaintiff(self, mock_signals_service):
        """测试获取推荐文书类型（原告方）"""
        from apps.core.enums import LegalStatus
        from apps.litigation_ai.models.choices import DocumentType

        mock_case_service = Mock()
        mock_case = Mock()
        mock_case.id = self.case_id
        self.service.case_service = mock_case_service
        mock_case_service.get_case_internal.return_value = mock_case

        mock_party = Mock()
        mock_party.legal_status = LegalStatus.PLAINTIFF
        mock_case_service.get_case_parties_internal.return_value = [mock_party]

        mock_signals = Mock()
        mock_signals.has_counterclaim = False
        mock_signals_service.return_value.get_signals_internal.return_value = mock_signals

        result = self.service.get_recommended_document_types(case_id=self.case_id)

        assert DocumentType.COMPLAINT in result
        assert DocumentType.COUNTERCLAIM_DEFENSE not in result

    @patch("apps.litigation_ai.services.wiring.get_court_pleading_signals_service")
    def test_get_recommended_document_types_defendant(self, mock_signals_service):
        """测试获取推荐文书类型（被告方）"""
        from apps.core.enums import LegalStatus
        from apps.litigation_ai.models.choices import DocumentType

        mock_case_service = Mock()
        mock_case = Mock()
        mock_case.id = self.case_id
        self.service.case_service = mock_case_service
        mock_case_service.get_case_internal.return_value = mock_case

        mock_party = Mock()
        mock_party.legal_status = LegalStatus.DEFENDANT
        mock_case_service.get_case_parties_internal.return_value = [mock_party]

        mock_signals = Mock()
        mock_signals.has_counterclaim = False
        mock_signals_service.return_value.get_signals_internal.return_value = mock_signals

        result = self.service.get_recommended_document_types(case_id=self.case_id)

        assert DocumentType.DEFENSE in result
        assert DocumentType.COUNTERCLAIM in result

    def test_get_recommended_document_types_case_not_found(self):
        """测试获取推荐文书类型时案件不存在"""
        mock_case_service = Mock()
        mock_case_service.get_case_internal.return_value = None
        self.service.case_service = mock_case_service

        with pytest.raises(NotFoundError) as exc_info:
            self.service.get_recommended_document_types(case_id=999)

        assert "案件不存在" in exc_info.value.message  # type: ignore[operator]
        assert exc_info.value.code == "CASE_NOT_FOUND"


@pytest.mark.django_db
class TestSessionLifecycleServiceDTO:
    """会话生命周期服务 DTO 转换测试"""

    def setup_method(self):
        self.service = SessionLifecycleService()
        self.case = _make_case("dto_case")
        self.lawyer = _make_lawyer("dto_lawyer")

    def test_to_session_dto(self):
        """测试 _to_session_dto 转换"""
        from apps.litigation_ai.models import LitigationSession

        session = LitigationSession.objects.create(
            case_id=self.case.id, user_id=self.lawyer.id, status="active", metadata={"key": "value"}
        )

        dto = self.service._to_session_dto(session)

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

        session = LitigationSession.objects.create(
            case_id=self.case.id, user_id=self.lawyer.id, status="active", metadata={}
        )
        session = LitigationSession.objects.select_related("case").get(id=session.id)

        dto = self.service._to_session_dto(session)

        assert dto.case_name == "dto_case"


@pytest.mark.django_db
class TestSessionLifecycleServiceEdgeCases:
    """会话生命周期服务边界情况测试"""

    def setup_method(self):
        self.service = SessionLifecycleService()
        self.case = _make_case("edge_case")
        self.lawyer = _make_lawyer("edge_lawyer")
        self.case_id = self.case.id
        self.user_id = self.lawyer.id

    def test_update_session_metadata_merge(self):
        """测试更新会话元数据合并"""
        session_dto = self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        self.service.update_session_status(
            session_id=session_dto.session_id, status="active", metadata_updates={"key1": "value1"}
        )
        updated_dto = self.service.update_session_status(
            session_id=session_dto.session_id, status="active", metadata_updates={"key2": "value2"}
        )

        assert updated_dto.metadata["key1"] == "value1"
        assert updated_dto.metadata["key2"] == "value2"

    def test_list_sessions_empty_result(self):
        """测试列出会话为空"""
        result = self.service.list_sessions()

        assert result["total"] == 0
        assert len(result["sessions"]) == 0

    def test_list_sessions_with_message_count(self):
        """测试列出会话包含消息数量"""
        self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        result = self.service.list_sessions()

        assert "message_count" in result["sessions"][0]
        assert result["sessions"][0]["message_count"] >= 0

    def test_create_session_with_metadata(self):
        """测试创建会话时元数据初始化"""
        session_dto = self.service.create_session(case_id=self.case_id, user_id=self.user_id)

        assert isinstance(session_dto.metadata, dict)
        assert len(session_dto.metadata) == 0
