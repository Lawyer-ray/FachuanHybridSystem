"""
ContractGenerationService 单元测试

测试合同生成服务的核心功能。
"""

from datetime import date
from io import BytesIO
from unittest.mock import MagicMock, mock_open, patch

import pytest

from apps.client.models import Client
from apps.contracts.models import Contract, ContractAssignment, ContractParty, PartyRole
from apps.core.exceptions import NotFoundError
from apps.documents.models import DocumentTemplate, DocumentTemplateType
from apps.documents.services.generation.contract_generation_service import ContractGenerationService
from apps.organization.models import Lawyer


@pytest.fixture
def contract_generation_service():
    """创建 ContractGenerationService 实例"""
    return ContractGenerationService()


@pytest.fixture
def mock_contract(db):
    """创建测试用合同"""
    # 创建律师
    lawyer1 = Lawyer.objects.create(username="lawyer1", real_name="张律师", email="zhang@example.com")
    lawyer2 = Lawyer.objects.create(username="lawyer2", real_name="李律师", email="li@example.com")

    # 创建客户
    client1 = Client.objects.create(
        name="委托人甲",
        client_type=Client.NATURAL,
        id_number="110101199001011234",
        address="北京市朝阳区",
        phone="13800138001",
    )
    client2 = Client.objects.create(
        name="对方当事人乙",
        client_type=Client.LEGAL,
        id_number="91110000123456789X",
        legal_representative="王总",
        address="北京市海淀区",
        phone="13800138002",
    )

    # 创建合同
    contract = Contract.objects.create(
        name="测试合同", case_type="civil", representation_stages=["first_trial", "appeal"]
    )

    # 创建合同当事人
    ContractParty.objects.create(contract=contract, client=client1, role=PartyRole.PRINCIPAL)
    ContractParty.objects.create(contract=contract, client=client2, role=PartyRole.OPPOSING)

    # 创建律师指派
    ContractAssignment.objects.create(contract=contract, lawyer=lawyer1, is_primary=True)
    ContractAssignment.objects.create(contract=contract, lawyer=lawyer2, is_primary=False)

    return contract


@pytest.fixture
def mock_template(db):
    """创建测试用模板"""
    return DocumentTemplate.objects.create(
        name="合同模板",
        template_type=DocumentTemplateType.CONTRACT,
        contract_types=["civil"],
        file_path="templates/contract.docx",
        is_active=True,
    )


class TestContractGenerationService:
    """合同生成服务单元测试"""

    def test_find_matching_template_success(self, contract_generation_service, mock_template):
        """测试成功查找匹配模板"""
        result = contract_generation_service.find_matching_template("civil")

        assert result is not None
        assert result.id == mock_template.id
        assert result.template_type == DocumentTemplateType.CONTRACT

    def test_find_matching_template_with_all_type(self, contract_generation_service, db):
        """测试查找包含 'all' 的通用模板"""
        template = DocumentTemplate.objects.create(
            name="通用合同模板",
            template_type=DocumentTemplateType.CONTRACT,
            contract_types=["all"],
            file_path="templates/universal.docx",
            is_active=True,
        )

        result = contract_generation_service.find_matching_template("criminal")

        assert result is not None
        assert result.id == template.id

    def test_find_matching_template_not_found(self, contract_generation_service, db):
        """测试未找到匹配模板"""
        result = contract_generation_service.find_matching_template("nonexistent")

        assert result is None

    def test_find_matching_template_inactive(self, contract_generation_service, db):
        """测试不返回未激活的模板"""
        DocumentTemplate.objects.create(
            name="未激活模板",
            template_type=DocumentTemplateType.CONTRACT,
            contract_types=["civil"],
            file_path="templates/inactive.docx",
            is_active=False,
        )

        result = contract_generation_service.find_matching_template("civil")

        assert result is None

    def test_build_context_basic(self, contract_generation_service, mock_contract):
        """测试基本上下文构建"""
        context = contract_generation_service.build_context(mock_contract)

        # 验证年份
        assert context["年份"] == str(date.today().year)

        # 验证对方当事人名称
        assert context["对方当事人名称"] == "对方当事人乙"

        # 验证代理阶段（转换为字符串）
        stage_text = context["代理阶段"]
        assert isinstance(stage_text, str)
        assert len(stage_text) > 0

        # 验证律师姓名（主办律师在前）
        assert context["律师姓名"].startswith("张律师")
        assert "李律师" in context["律师姓名"]

        # 验证委托人信息
        assert "甲方：委托人甲" in context["委托人信息"]
        assert "身份证号码：110101199001011234" in context["委托人信息"]

    def test_build_context_multiple_opposing_parties(self, contract_generation_service, mock_contract):
        """测试多个对方当事人的上下文构建"""
        # 添加另一个对方当事人
        client3 = Client.objects.create(name="对方当事人丙", client_type=Client.NATURAL, id_number="110101199002021234")
        ContractParty.objects.create(contract=mock_contract, client=client3, role=PartyRole.OPPOSING)

        context = contract_generation_service.build_context(mock_contract)

        # 验证多个对方当事人用顿号分隔
        opposing_names = context["对方当事人名称"]
        assert "对方当事人乙" in opposing_names
        assert "对方当事人丙" in opposing_names
        assert "、" in opposing_names

    def test_build_context_single_natural_person(self, contract_generation_service, db):
        """测试单个自然人委托人的上下文构建"""
        client = Client.objects.create(
            name="张三",
            client_type=Client.NATURAL,
            id_number="110101199001011234",
            address="北京市朝阳区",
            phone="13800138001",
        )

        contract = Contract.objects.create(name="测试", case_type="civil")
        ContractParty.objects.create(contract=contract, client=client, role=PartyRole.PRINCIPAL)

        context = contract_generation_service.build_context(contract)

        # 验证委托人信息包含正确内容
        principal_info = context.get("委托人信息", "")
        assert "甲方：张三" in principal_info
        assert "身份证号码：110101199001011234" in principal_info
        assert "地址：北京市朝阳区" in principal_info
        assert "电话：13800138001" in principal_info
        assert "统一社会信用代码" not in principal_info

    def test_build_context_single_legal_entity(self, contract_generation_service, db):
        """测试单个法人委托人的上下文构建"""
        client = Client.objects.create(
            name="某某公司",
            client_type=Client.LEGAL,
            id_number="91110000123456789X",
            legal_representative="王总",
            address="北京市海淀区",
            phone="010-12345678",
        )

        contract = Contract.objects.create(name="测试", case_type="civil")
        ContractParty.objects.create(contract=contract, client=client, role=PartyRole.PRINCIPAL)

        context = contract_generation_service.build_context(contract)

        # 验证委托人信息包含正确内容
        principal_info = context.get("委托人信息", "")
        assert "甲方：某某公司" in principal_info
        assert "统一社会信用代码：91110000123456789X" in principal_info
        assert "法定代表人：王总" in principal_info
        assert "地址：北京市海淀区" in principal_info
        assert "电话：010-12345678" in principal_info
        assert "身份证号码" not in principal_info

    def test_build_context_multiple_principals(self, contract_generation_service, db):
        """测试多个委托人的上下文构建"""
        client1 = Client.objects.create(name="张三", client_type=Client.NATURAL, id_number="110101199001011234")
        client2 = Client.objects.create(name="李四", client_type=Client.NATURAL, id_number="110101199002021234")

        contract = Contract.objects.create(name="测试", case_type="civil")
        ContractParty.objects.create(contract=contract, client=client1, role=PartyRole.PRINCIPAL)
        ContractParty.objects.create(contract=contract, client=client2, role=PartyRole.PRINCIPAL)

        context = contract_generation_service.build_context(contract)

        # 验证委托人信息包含正确内容
        principal_info = context.get("委托人信息", "")
        assert "甲方一：张三" in principal_info
        assert "甲方二：李四" in principal_info

    def test_generate_filename(self, contract_generation_service, mock_template):
        """测试文件名生成"""
        contract = Contract(name="民事代理合同")

        result = contract_generation_service.generate_filename(contract, mock_template)

        today = date.today().strftime("%Y%m%d")
        expected = f"合同模板（民事代理合同）V1_{today}.docx"

        assert result == expected

    @patch("pathlib.Path.exists")
    @patch("docxtpl.DocxTemplate")
    def test_generate_contract_document_success(
        self, mock_docx_template, mock_path_exists, contract_generation_service, mock_contract, mock_template
    ):
        """测试成功生成合同文档"""
        # Mock 文件存在
        mock_path_exists.return_value = True

        # Mock 模板文件路径
        mock_template.get_file_location = MagicMock(return_value="/path/to/template.docx")

        # Mock DocxTemplate
        mock_doc = MagicMock()
        mock_docx_template.return_value = mock_doc

        # Mock 保存到内存
        mock_output = BytesIO()
        mock_output.write(b"fake docx content")
        mock_output.seek(0)
        mock_doc.save = MagicMock(side_effect=lambda output: output.write(b"fake docx content"))

        with patch.object(contract_generation_service, "find_matching_template", return_value=mock_template):
            content, filename, error = contract_generation_service.generate_contract_document(mock_contract.id)

        assert content is not None
        assert filename is not None
        assert error is None
        assert filename.startswith("合同模板（测试合同）V1_")
        assert filename.endswith(".docx")

    @pytest.mark.django_db
    def test_generate_contract_document_contract_not_found(self, contract_generation_service):
        """测试合同不存在的情况"""
        content, filename, error = contract_generation_service.generate_contract_document(99999)

        assert content is None
        assert filename is None
        assert error == "合同不存在"

    def test_generate_contract_document_template_not_found(self, contract_generation_service, mock_contract):
        """测试模板不存在的情况"""
        with patch.object(contract_generation_service, "find_matching_template", return_value=None):
            content, filename, error = contract_generation_service.generate_contract_document(mock_contract.id)

        assert content is None
        assert filename is None
        assert error == "请先添加合同模板"

    @patch("pathlib.Path.exists")
    def test_generate_contract_document_template_file_not_found(
        self, mock_path_exists, contract_generation_service, mock_contract, mock_template
    ):
        """测试模板文件不存在的情况"""
        # Mock 文件不存在
        mock_path_exists.return_value = False
        mock_template.get_file_location = MagicMock(return_value="/path/to/nonexistent.docx")

        with patch.object(contract_generation_service, "find_matching_template", return_value=mock_template):
            content, filename, error = contract_generation_service.generate_contract_document(mock_contract.id)

        assert content is None
        assert filename is None
        assert error == "模板文件不存在"

    @patch("pathlib.Path.exists")
    @patch("docxtpl.DocxTemplate")
    def test_generate_contract_document_render_error(
        self, mock_docx_template, mock_path_exists, contract_generation_service, mock_contract, mock_template
    ):
        """测试模板渲染错误的情况"""
        # Mock 文件存在
        mock_path_exists.return_value = True
        mock_template.get_file_location = MagicMock(return_value="/path/to/template.docx")

        # Mock DocxTemplate 抛出异常
        mock_docx_template.side_effect = Exception("渲染失败")

        with patch.object(contract_generation_service, "find_matching_template", return_value=mock_template):
            content, filename, error = contract_generation_service.generate_contract_document(mock_contract.id)

        assert content is None
        assert filename is None
        assert "生成合同失败" in error
        assert "渲染失败" in error
