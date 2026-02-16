import pytest
from unittest.mock import MagicMock, Mock

from apps.cases.services.template.case_template_binding_service import CaseTemplateBindingService
from apps.cases.services.template.repo import CaseTemplateBindingRepo
from apps.cases.services.template.template_binding_assembler import TemplateBindingAssembler
from apps.cases.services.template.template_match_policy import CaseTemplateMatchPolicy
from apps.core.exceptions import ConflictError, NotFoundError
from apps.cases.models import BindingSource, Case, CaseTemplateBinding

@pytest.mark.django_db
class TestCaseTemplateBindingService:
    @pytest.fixture
    def mock_document_service(self):
        return Mock()

    @pytest.fixture
    def mock_repo(self):
        return Mock(spec=CaseTemplateBindingRepo)

    @pytest.fixture
    def service(self, mock_document_service, mock_repo):
        return CaseTemplateBindingService(
            document_service=mock_document_service,
            repo=mock_repo
        )

    def test_bind_template_success(self, service, mock_repo, mock_document_service):
        case_id = 1
        template_id = 101
        
        # Setup mocks
        mock_repo.get_case.return_value = Mock(id=case_id)
        mock_repo.exists_binding.return_value = False
        
        mock_template = Mock(id=template_id)
        mock_template.name = "Test Template"
        mock_document_service.get_template_by_id_internal.return_value = mock_template
        
        mock_binding = Mock(
            id=1, 
            binding_source=BindingSource.MANUAL_BOUND,
            created_at=None,
            get_binding_source_display=lambda: "手动绑定"
        )
        mock_repo.create_binding.return_value = mock_binding

        # Execute
        result = service.bind_template(case_id, template_id)

        # Verify
        mock_repo.get_case.assert_called_with(case_id)
        mock_repo.exists_binding.assert_called_with(case_id, template_id)
        mock_repo.create_binding.assert_called_with(case_id=case_id, template_id=template_id, source=BindingSource.MANUAL_BOUND)
        
        assert result["binding_id"] == 1
        assert result["template_id"] == template_id
        assert result["name"] == "Test Template"

    def test_bind_template_already_exists(self, service, mock_repo, mock_document_service):
        case_id = 1
        template_id = 101
        
        mock_repo.get_case.return_value = Mock(id=case_id)
        mock_template = Mock(id=template_id)
        mock_document_service.get_template_by_id_internal.return_value = mock_template
        mock_repo.exists_binding.return_value = True

        with pytest.raises(ConflictError):
            service.bind_template(case_id, template_id)

    def test_unbind_template_success(self, service, mock_repo):
        case_id = 1
        binding_id = 10
        
        mock_repo.get_case.return_value = Mock(id=case_id)
        mock_binding = Mock(id=binding_id, binding_source=BindingSource.MANUAL_BOUND, template_id=101)
        mock_repo.get_binding.return_value = mock_binding
        
        service.unbind_template(case_id, binding_id)
        
        mock_repo.delete_binding.assert_called_with(mock_binding)

    def test_unbind_auto_recommended_fails(self, service, mock_repo):
        case_id = 1
        binding_id = 10
        
        mock_repo.get_case.return_value = Mock(id=case_id)
        mock_binding = Mock(id=binding_id, binding_source=BindingSource.AUTO_RECOMMENDED, template_id=101)
        mock_repo.get_binding.return_value = mock_binding
        
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="自动推荐的模板不能手动移除"):
            service.unbind_template(case_id, binding_id)
