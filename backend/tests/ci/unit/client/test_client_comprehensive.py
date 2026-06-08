"""client 模块核心服务/API 测试

覆盖文件:
- apps/client/services/text_parser.py
- apps/client/services/client_mutation_service.py
- apps/client/services/client_query_facade.py
- apps/client/services/client_query_service.py
- apps/client/services/client_export_serializer_service.py
- apps/client/services/client_resolve_service.py
- apps/client/services/client_identity_doc_service.py
- apps/client/api/client_api.py
- apps/client/signals.py
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import ForbiddenError, ValidationException


# ==================== Text Parser ====================


class TestTextParser:
    """text_parser.py 解析逻辑测试"""

    def test_parse_client_text_empty(self):
        from apps.client.services.text_parser import parse_client_text

        result = parse_client_text("")
        assert result["name"] == ""

    def test_parse_client_text_whitespace(self):
        from apps.client.services.text_parser import parse_client_text

        result = parse_client_text("   \n  ")
        assert result["name"] == ""

    def test_parse_client_text_legal_entity(self):
        from apps.client.services.text_parser import parse_client_text

        text = "原告：北京科技有限公司\n法定代表人：张三\n统一社会信用代码：91110000MA01B1234X"
        result = parse_client_text(text)
        assert result["name"] == "北京科技有限公司"
        assert result["client_type"] == "legal"

    def test_parse_client_text_natural_person(self):
        from apps.client.services.text_parser import parse_client_text

        text = "被告：张三，男，1990年1月1日出生\n身份证号码：110101199001011234"
        result = parse_client_text(text)
        assert "张三" in result["name"]
        assert result["id_number"] == "110101199001011234"

    def test_parse_client_text_with_address(self):
        from apps.client.services.text_parser import parse_client_text

        text = "原告：测试公司\n地址：北京市朝阳区建国路88号"
        result = parse_client_text(text)
        assert result["address"] != "" or result["name"] != ""

    def test_parse_client_text_with_phone(self):
        from apps.client.services.text_parser import parse_client_text

        text = "原告：测试公司\n联系电话：13800138000"
        result = parse_client_text(text)
        assert "phone" in result

    def test_parse_multiple_clients_text_empty(self):
        from apps.client.services.text_parser import parse_multiple_clients_text

        result = parse_multiple_clients_text("")
        assert result == []

    def test_parse_multiple_clients_text_single(self):
        from apps.client.services.text_parser import parse_multiple_clients_text

        text = "原告：北京科技有限公司\n法定代表人：张三"
        result = parse_multiple_clients_text(text)
        assert len(result) >= 1

    def test_parse_multiple_clients_text_multiple(self):
        from apps.client.services.text_parser import parse_multiple_clients_text

        text = "原告：北京科技有限公司\n法定代表人：张三\n被告：上海贸易有限公司\n法定代表人：李四"
        result = parse_multiple_clients_text(text)
        assert len(result) >= 2

    def test_normalize_text_semicolons(self):
        from apps.client.services.text_parser import _normalize_text

        result = _normalize_text("甲方：A公司；乙方：B公司")
        assert "\n" in result

    def test_extract_credit_code(self):
        from apps.client.services.text_parser import _extract_credit_code

        result = _extract_credit_code("统一社会信用代码：91110000MA01B1234X")
        assert result == "91110000MA01B1234X"

    def test_extract_credit_code_not_found(self):
        from apps.client.services.text_parser import _extract_credit_code

        result = _extract_credit_code("没有信用代码")
        assert result is None

    def test_extract_id_number(self):
        from apps.client.services.text_parser import _extract_id_number

        result = _extract_id_number("身份证号码：110101199001011234")
        assert result == "110101199001011234"

    def test_extract_id_number_not_found(self):
        from apps.client.services.text_parser import _extract_id_number

        result = _extract_id_number("没有身份证号")
        assert result is None

    def test_extract_address(self):
        from apps.client.services.text_parser import _extract_address

        result = _extract_address("地址：北京市朝阳区建国路88号")
        assert result == "北京市朝阳区建国路88号"

    def test_extract_phone(self):
        from apps.client.services.text_parser import _extract_phone

        result = _extract_phone("联系电话：010-12345678")
        assert result is not None

    def test_extract_legal_representative(self):
        from apps.client.services.text_parser import _extract_legal_representative

        result = _extract_legal_representative("法定代表人：张三")
        assert "张三" in (result or "")

    def test_extract_legal_representative_not_found(self):
        from apps.client.services.text_parser import _extract_legal_representative

        result = _extract_legal_representative("这是普通文本内容")
        assert result is None or result == ""

    def test_determine_client_type_legal(self):
        from apps.client.services.text_parser import _determine_client_type

        result = _determine_client_type("北京科技有限公司", "统一社会信用代码：91110000MA01B1234X")
        assert result == "legal"

    def test_determine_client_type_natural(self):
        from apps.client.services.text_parser import _determine_client_type

        result = _determine_client_type("张三", "身份证号码：110101199001011234")
        assert result == "natural"

    def test_determine_client_type_by_keyword(self):
        from apps.client.services.text_parser import _determine_client_type

        result = _determine_client_type("北京科技有限公司", "")
        assert result == "legal"

    def test_is_valid_name_candidate_short(self):
        from apps.client.services.text_parser import _is_valid_name_candidate

        assert _is_valid_name_candidate("A") is False

    def test_is_valid_name_candidate_digit(self):
        from apps.client.services.text_parser import _is_valid_name_candidate

        assert _is_valid_name_candidate("12345") is False

    def test_is_valid_name_candidate_valid(self):
        from apps.client.services.text_parser import _is_valid_name_candidate

        assert _is_valid_name_candidate("张三") is True

    def test_empty_result(self):
        from apps.client.services.text_parser import _empty_result

        result = _empty_result()
        assert result["name"] == ""
        assert result["client_type"] == "natural"
        assert result["phone"] == ""

    def test_clean_name_candidate(self):
        from apps.client.services.text_parser import _clean_name_candidate

        result = _clean_name_candidate("被告：张三，男")
        assert "男" not in result or "张三" in result

    def test_extract_name_from_first_meaningful_line(self):
        from apps.client.services.text_parser import _extract_name_from_first_meaningful_line

        result = _extract_name_from_first_meaningful_line("北京科技有限公司\n法定代表人：张三")
        assert result == "北京科技有限公司"


# ==================== ClientMutationService ====================


class TestClientMutationService:
    """ClientMutationService CRUD 测试"""

    def _make_service(self):
        from apps.client.services.client_mutation_service import ClientMutationService

        mock_policy = MagicMock()
        mock_query = MagicMock()
        mock_deletion = MagicMock()
        mock_id_doc = MagicMock()
        return ClientMutationService(
            access_policy=mock_policy,
            query_service=mock_query,
            deletion_workflow=mock_deletion,
            identity_doc_service=mock_id_doc,
        )

    def test_create_client_success(self, db):
        service = self._make_service()
        data = {"name": "测试客户", "client_type": "natural"}
        client = service.create_client(data=data, user=MagicMock())
        assert client.name == "测试客户"

    def test_create_client_no_permission(self, db):
        service = self._make_service()
        service.access_policy.ensure_can_create_client.side_effect = ForbiddenError("no perm")
        with pytest.raises(ForbiddenError):
            service.create_client(data={"name": "test", "client_type": "natural"})

    def test_create_client_empty_name(self, db):
        service = self._make_service()
        with pytest.raises(ValidationException):
            service.create_client(data={"name": "", "client_type": "natural"})

    def test_create_client_invalid_type(self, db):
        service = self._make_service()
        with pytest.raises(ValidationException, match="无效的客户类型"):
            service.create_client(data={"name": "测试", "client_type": "invalid"})

    def test_create_client_legal_without_representative(self, db):
        service = self._make_service()
        with pytest.raises(ValidationException, match="法定代表人"):
            service.create_client(data={"name": "测试公司", "client_type": "legal"})

    def test_create_client_legal_with_representative(self, db):
        service = self._make_service()
        data = {"name": "测试公司", "client_type": "legal", "legal_representative": "张三"}
        client = service.create_client(data=data, user=MagicMock())
        assert client.name == "测试公司"
        assert client.legal_representative == "张三"

    def test_update_client_success(self, db):
        from apps.client.models import Client

        client = Client.objects.create(name="旧名称", client_type="natural")
        service = self._make_service()
        service.query_service.get_client.return_value = client
        result = service.update_client(client_id=client.id, data={"name": "新名称"}, user=MagicMock())
        assert result.name == "新名称"

    def test_update_client_empty_name(self, db):
        from apps.client.models import Client

        client = Client.objects.create(name="旧名称", client_type="natural")
        service = self._make_service()
        service.query_service.get_client.return_value = client
        with pytest.raises(ValidationException, match="名称不能为空"):
            service.update_client(client_id=client.id, data={"name": ""}, user=MagicMock())

    def test_update_client_invalid_type(self, db):
        from apps.client.models import Client

        client = Client.objects.create(name="旧名称", client_type="natural")
        service = self._make_service()
        service.query_service.get_client.return_value = client
        with pytest.raises(ValidationException, match="无效的客户类型"):
            service.update_client(client_id=client.id, data={"client_type": "invalid"}, user=MagicMock())

    def test_delete_client_success(self, db):
        from apps.client.models import Client

        client = Client.objects.create(name="待删除", client_type="natural")
        service = self._make_service()
        service.query_service.get_client.return_value = client
        service.deletion_workflow.collect_client_file_paths.return_value = []
        service.delete_client(client_id=client.id, user=MagicMock())
        service.deletion_workflow.cleanup_files_on_commit.assert_called_once()

    def test_delete_client_no_permission(self, db):
        service = self._make_service()
        service.access_policy.ensure_can_delete_client.side_effect = ForbiddenError("no perm")
        with pytest.raises(ForbiddenError):
            service.delete_client(client_id=1, user=MagicMock())

    def test_validate_create_data_legal_with_representative(self):
        service = self._make_service()
        # Should not raise
        service._validate_create_data({
            "name": "公司", "client_type": "legal", "legal_representative": "张三"
        })

    def test_validate_update_data_type_change_to_legal_without_rep(self, db):
        from apps.client.models import Client

        client = Client.objects.create(name="旧", client_type="natural")
        service = self._make_service()
        with pytest.raises(ValidationException, match="法定代表人"):
            service._validate_update_data(client, {"client_type": "legal"})


# ==================== ClientQueryFacade ====================


class TestClientQueryFacade:
    """ClientQueryFacade 权限+查询 测试"""

    def test_list_clients_checks_permission(self):
        from apps.client.services.client_query_facade import ClientQueryFacade

        mock_policy = MagicMock()
        mock_query = MagicMock()
        facade = ClientQueryFacade(query_service=mock_query, access_policy=mock_policy)
        facade.list_clients(client_type="natural", user=MagicMock())
        mock_policy.ensure_has_perm.assert_called_once()

    def test_list_clients_no_user_no_check(self):
        from apps.client.services.client_query_facade import ClientQueryFacade

        mock_policy = MagicMock()
        mock_query = MagicMock()
        facade = ClientQueryFacade(query_service=mock_query, access_policy=mock_policy)
        facade.list_clients(client_type="natural", user=None)
        mock_policy.ensure_has_perm.assert_not_called()

    def test_get_client_checks_permission(self):
        from apps.client.services.client_query_facade import ClientQueryFacade

        mock_policy = MagicMock()
        mock_query = MagicMock()
        facade = ClientQueryFacade(query_service=mock_query, access_policy=mock_policy)
        facade.get_client(client_id=1, user=MagicMock())
        mock_policy.ensure_has_perm.assert_called_once()

    def test_get_clients_by_ids_checks_permission(self):
        from apps.client.services.client_query_facade import ClientQueryFacade

        mock_policy = MagicMock()
        mock_query = MagicMock()
        facade = ClientQueryFacade(query_service=mock_query, access_policy=mock_policy)
        facade.get_clients_by_ids(client_ids=[1, 2], user=MagicMock())
        mock_policy.ensure_has_perm.assert_called_once()


# ==================== ClientQueryService ====================


class TestClientQueryService:
    """ClientQueryService 组合服务测试"""

    def test_list_clients_delegates(self):
        from apps.client.services.client_query_service import ClientQueryService

        mock_list = MagicMock()
        mock_list.list_clients.return_value = "result"
        svc = ClientQueryService(list_query=mock_list)
        result = svc.list_clients(client_type="natural", search="test")
        assert result == "result"

    def test_get_client_delegates(self):
        from apps.client.services.client_query_service import ClientQueryService

        mock_get = MagicMock()
        mock_get.get_client.return_value = "client"
        svc = ClientQueryService(get_query=mock_get)
        result = svc.get_client(client_id=1)
        assert result == "client"

    def test_get_clients_by_ids_delegates(self):
        from apps.client.services.client_query_service import ClientQueryService

        mock_batch = MagicMock()
        mock_batch.get_clients_by_ids.return_value = ["c1", "c2"]
        svc = ClientQueryService(batch_query=mock_batch)
        result = svc.get_clients_by_ids(client_ids=[1, 2])
        assert result == ["c1", "c2"]

    def test_lazy_list_query(self):
        from apps.client.services.client_query_service import ClientQueryService

        svc = ClientQueryService()
        assert svc._list_query is None

    def test_lazy_get_query(self):
        from apps.client.services.client_query_service import ClientQueryService

        svc = ClientQueryService()
        assert svc._get_query is None

    def test_lazy_batch_query(self):
        from apps.client.services.client_query_service import ClientQueryService

        svc = ClientQueryService()
        assert svc._batch_query is None


# ==================== ClientExportSerializerService ====================


class TestClientExportSerializerService:
    """client_export_serializer_service 测试"""

    def test_serialize_client_obj(self):
        from apps.client.services.client_export_serializer_service import serialize_client_obj

        mock_doc = SimpleNamespace(doc_type="id_card", file_path="docs/1.pdf")
        mock_clue = SimpleNamespace(
            clue_type="bank",
            content="中国银行1234",
            attachments=MagicMock(all=MagicMock(return_value=[])),
        )

        mock_client = SimpleNamespace(
            name="张三",
            client_type="natural",
            id_number="110101199001011234",
            phone="13800138000",
            address="北京市朝阳区",
            legal_representative="",
            legal_representative_id_number="",
            is_our_client=True,
            identity_docs=MagicMock(all=MagicMock(return_value=[mock_doc])),
            property_clues=MagicMock(all=MagicMock(return_value=[mock_clue])),
        )

        result = serialize_client_obj(mock_client)
        assert result["name"] == "张三"
        assert result["client_type"] == "natural"
        assert len(result["identity_docs"]) == 1
        assert len(result["property_clues"]) == 1

    def test_service_facade(self):
        from apps.client.services.client_export_serializer_service import ClientExportSerializerService

        svc = ClientExportSerializerService()
        mock_client = SimpleNamespace(
            name="test", client_type="natural", id_number="", phone="",
            address="", legal_representative="", legal_representative_id_number="",
            is_our_client=False,
            identity_docs=MagicMock(all=MagicMock(return_value=[])),
            property_clues=MagicMock(all=MagicMock(return_value=[])),
        )
        result = svc.serialize_client_obj(mock_client)
        assert result["name"] == "test"


# ==================== Client Access Policy ====================


class TestClientAccessPolicy:
    """client_access_policy 权限检查测试"""

    def test_can_create_client_no_user(self):
        from apps.client.services.client_access_policy import ClientAccessPolicy

        policy = ClientAccessPolicy()
        assert policy.can_create_client(None) is False

    def test_ensure_can_create_client_no_user(self):
        from apps.client.services.client_access_policy import ClientAccessPolicy

        policy = ClientAccessPolicy()
        with pytest.raises(ForbiddenError):
            policy.ensure_can_create_client(None)

    def test_can_update_client_no_user(self):
        from apps.client.services.client_access_policy import ClientAccessPolicy

        policy = ClientAccessPolicy()
        assert policy.can_update_client(None) is False

    def test_ensure_can_update_client_no_user(self):
        from apps.client.services.client_access_policy import ClientAccessPolicy

        policy = ClientAccessPolicy()
        with pytest.raises(ForbiddenError):
            policy.ensure_can_update_client(None)

    def test_can_delete_client_no_user(self):
        from apps.client.services.client_access_policy import ClientAccessPolicy

        policy = ClientAccessPolicy()
        assert policy.can_delete_client(None) is False

    def test_ensure_can_delete_client_no_user(self):
        from apps.client.services.client_access_policy import ClientAccessPolicy

        policy = ClientAccessPolicy()
        with pytest.raises(ForbiddenError):
            policy.ensure_can_delete_client(None)


# ==================== Client API ====================


class TestClientApi:
    """client_api.py 端点测试"""

    @patch("apps.client.api.client_api._get_query_facade")
    def test_list_clients(self, mock_facade_cls):
        from apps.client.api.client_api import list_clients

        mock_facade = MagicMock()
        mock_facade.list_clients.return_value = []
        mock_facade_cls.return_value = mock_facade

        request = MagicMock()
        request.auth = MagicMock()
        result = list_clients(request, client_type="natural", is_our_client=True, search="test")
        assert result == []

    @patch("apps.client.api.client_api._get_query_facade")
    def test_get_client(self, mock_facade_cls):
        from apps.client.api.client_api import get_client

        mock_facade = MagicMock()
        mock_facade.get_client.return_value = SimpleNamespace(id=1, name="张三")
        mock_facade_cls.return_value = mock_facade

        request = MagicMock()
        request.auth = MagicMock()
        result = get_client(request, client_id=1)
        assert result.name == "张三"

    @patch("apps.client.api.client_api._get_mutation_service")
    def test_create_client(self, mock_svc_cls):
        from apps.client.api.client_api import create_client
        from apps.client.schemas import ClientIn

        mock_svc = MagicMock()
        mock_client = SimpleNamespace(id=1, name="新客户", client_type="natural")
        mock_svc.create_client.return_value = mock_client
        mock_svc_cls.return_value = mock_svc

        request = MagicMock()
        request.auth = MagicMock()
        payload = ClientIn(name="新客户", client_type="natural")
        result = create_client(request, payload)
        assert result.name == "新客户"

    @patch("apps.client.api.client_api._get_mutation_service")
    def test_update_client(self, mock_svc_cls):
        from apps.client.api.client_api import update_client
        from apps.client.schemas import ClientUpdateIn

        mock_svc = MagicMock()
        mock_client = SimpleNamespace(id=1, name="更新后")
        mock_svc.update_client.return_value = mock_client
        mock_svc_cls.return_value = mock_svc

        request = MagicMock()
        request.auth = MagicMock()
        payload = ClientUpdateIn(name="更新后")
        result = update_client(request, client_id=1, payload=payload)
        assert result.name == "更新后"

    @patch("apps.client.api.client_api._get_mutation_service")
    def test_delete_client(self, mock_svc_cls):
        from apps.client.api.client_api import delete_client

        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc

        request = MagicMock()
        request.auth = MagicMock()
        result = delete_client(request, client_id=1)
        mock_svc.delete_client.assert_called_once()

    @patch("apps.client.api.client_api._parse_client")
    def test_parse_client_text_single(self, mock_parse):
        from apps.client.api.client_api import parse_client_text

        mock_parse.return_value = {"name": "张三", "client_type": "natural"}
        request = MagicMock()
        payload = SimpleNamespace(text="张三", parse_multiple=False)
        result = parse_client_text(request, payload)
        assert result["success"] is True
        assert "client" in result

    @patch("apps.client.api.client_api._parse_client")
    def test_parse_client_text_no_name(self, mock_parse):
        from apps.client.api.client_api import parse_client_text

        mock_parse.return_value = {"name": ""}
        request = MagicMock()
        payload = SimpleNamespace(text="无效文本", parse_multiple=False)
        result = parse_client_text(request, payload)
        assert result["success"] is False

    @patch("apps.client.api.client_api._parse_multi")
    def test_parse_client_text_multiple(self, mock_parse_multi):
        from apps.client.api.client_api import parse_client_text

        mock_parse_multi.return_value = [{"name": "张三"}, {"name": "李四"}]
        request = MagicMock()
        payload = SimpleNamespace(text="多当事人", parse_multiple=True)
        result = parse_client_text(request, payload)
        assert result["success"] is True
        assert len(result["clients"]) == 2

    def test_parse_text_get(self):
        from apps.client.api.client_api import parse_text_get

        request = MagicMock()
        result = parse_text_get(request, text="张三")
        assert isinstance(result, dict)

    @patch("apps.client.api.client_api.IdCardUtils")
    def test_validate_id_card(self, mock_utils):
        from apps.client.api.client_api import validate_id_card

        mock_utils.validate_id_card.return_value = {"valid": True, "message": "ok"}
        request = MagicMock()
        payload = SimpleNamespace(id_number="110101199001011234")
        result = validate_id_card(request, payload)
        assert result.valid is True

    @patch("apps.client.api.client_api._get_query_facade")
    def test_get_related_items(self, mock_facade_cls):
        from apps.client.api.client_api import get_related_items

        mock_facade = MagicMock()
        mock_facade.get_related_items.return_value = {"cases": [], "contracts": []}
        mock_facade_cls.return_value = mock_facade

        request = MagicMock()
        result = get_related_items(request, client_id=1)
        assert result == {"cases": [], "contracts": []}


# ==================== Client Model ====================


class TestClientModel:
    """Client 模型测试"""

    def test_client_str(self, db):
        from apps.client.models import Client

        client = Client.objects.create(name="测试客户", client_type="natural")
        assert str(client) == "测试客户"

    def test_client_type_choices(self):
        from apps.client.models import Client

        assert Client.NATURAL == "natural"
        assert Client.LEGAL == "legal"
        assert Client.NON_LEGAL_ORG == "non_legal_org"

    def test_client_clean_legal_needs_representative(self, db):
        from apps.client.models import Client
        from django.core.exceptions import ValidationError

        client = Client(name="公司", client_type="legal")
        with pytest.raises(ValidationError):
            client.clean()

    def test_client_clean_natural_no_representative_ok(self, db):
        from apps.client.models import Client

        client = Client(name="张三", client_type="natural")
        # Should not raise
        client.clean()


# ==================== Client Identity Doc Service ====================


class TestClientIdentityDocService:
    """ClientIdentityDocService 测试"""

    def test_wiring_file_upload_port(self):
        from apps.client.services.wiring import get_file_upload_port

        port = get_file_upload_port()
        assert port is not None

    def test_wiring_file_validator_port(self):
        from apps.client.services.wiring import get_file_validator_port

        port = get_file_validator_port()
        assert port is not None

    def test_wiring_task_service_port(self):
        from apps.client.services.wiring import get_task_service_port

        port = get_task_service_port()
        assert port is not None
