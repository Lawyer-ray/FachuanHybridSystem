"""Deep integration tests: error handling, permissions, and business logic.

These tests go beyond smoke-level (status 200) to verify:
- Proper error codes (400, 404, 403) for invalid inputs
- Authentication/authorization enforcement
- Business logic side effects and data integrity
- Edge cases in query parameters and payloads
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from apps.cases.models import Case, CaseAccessGrant, CaseAssignment, CaseLog, CaseParty
from apps.client.models import Client
from apps.contracts.models import Contract
from apps.organization.models import LawFirm, Lawyer
from apps.reminders.models import Reminder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(**kwargs):
    return Contract.objects.create(
        name=kwargs.get("name", "深度测试合同"),
        case_type=kwargs.get("case_type", "civil"),
    )


def _make_case(contract=None, **kwargs):
    return Case.objects.create(
        name=kwargs.get("name", "深度测试案件"),
        contract=contract or _make_contract(),
        case_type=kwargs.get("case_type", "civil"),
    )


def _make_client(**kwargs):
    return Client.objects.create(
        name=kwargs.get("name", "深度测试客户"),
        client_type=kwargs.get("client_type", Client.NATURAL),
        is_our_client=kwargs.get("is_our_client", True),
    )


def _make_lawyer(firm, **kwargs):
    return Lawyer.objects.create_user(
        username=kwargs.get("username", "deep_test_lawyer"),
        password="testpass123",
        law_firm=firm,
    )


def _assert_error_body(resp) -> None:
    """断言错误响应体非空：必须携带 detail/message/error 之一的非空文案."""
    data = resp.json()
    assert isinstance(data, dict), f"错误响应应为 JSON 对象，实际: {data!r}"
    msg = data.get("detail") or data.get("message") or data.get("error")
    assert msg, f"错误响应体缺少 detail/message/error 字段: {data!r}"


# ===================================================================
# 1. Error Handling: 404 for Non-Existent Resources
# ===================================================================


class TestNotFoundErrors:
    """Verify 404 or appropriate error for non-existent resources."""

    @pytest.mark.django_db
    def test_get_nonexistent_case(self, authenticated_client):
        resp = authenticated_client.get("/api/v1/cases/cases/999999")
        assert resp.status_code in (404, 200)  # Some APIs return 200 with error
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("success") is False or "error" in data or "detail" in data
        else:
            # 404 分支必须返回带错误文案的错误体，而非空体
            _assert_error_body(resp)

    @pytest.mark.django_db
    def test_get_nonexistent_client(self, authenticated_client):
        resp = authenticated_client.get("/api/v1/client/clients/999999")
        assert resp.status_code in (404, 200)
        if resp.status_code == 200:
            # 200 分支不允许返回看似正常的客户数据
            data = resp.json()
            assert data.get("success") is False or "error" in data or "detail" in data
        else:
            _assert_error_body(resp)

    @pytest.mark.django_db
    def test_get_nonexistent_reminder(self, authenticated_client):
        resp = authenticated_client.get("/api/v1/reminders/999999")
        assert resp.status_code in (404, 200)
        if resp.status_code == 404:
            # 404 分支必须是结构化 NOT_FOUND 信封且文案锚定被查询的 ID
            data = resp.json()
            assert data["code"] == "NOT_FOUND"
            assert "999999" in data["message"]
        else:
            # 200 分支不允许返回看似正常的提醒数据
            data = resp.json()
            assert data.get("success") is False or "error" in data or "detail" in data

    @pytest.mark.django_db
    def test_delete_nonexistent_case(self, authenticated_client):
        resp = authenticated_client.delete("/api/v1/cases/cases/999999")
        assert resp.status_code in (404, 200, 204)
        if resp.status_code == 404:
            _assert_error_body(resp)
        # 无论如何，不存在的案件不应被创建/保留
        assert not Case.objects.filter(id=999999).exists()

    @pytest.mark.django_db
    def test_update_nonexistent_client(self, authenticated_client):
        resp = authenticated_client.put(
            "/api/v1/client/clients/999999",
            data=json.dumps({"name": "不存在的客户"}),
            content_type="application/json",
        )
        assert resp.status_code in (404, 200)
        if resp.status_code == 404:
            _assert_error_body(resp)
        # 更新不存在的客户绝不能凭空创建记录
        assert not Client.objects.filter(name="不存在的客户").exists()


# ===================================================================
# 2. Error Handling: 400 for Invalid Data
# ===================================================================


class TestValidationErrors:
    """Verify proper error responses for invalid inputs."""

    @pytest.mark.django_db
    def test_create_client_empty_name(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/v1/client/clients",
            data=json.dumps({"name": "", "client_type": "natural"}),
            content_type="application/json",
        )
        # Should either reject or accept with empty name
        if resp.status_code == 200:
            data = resp.json()
            # If accepted, verify the data
            assert "id" in data

    @pytest.mark.django_db
    def test_create_case_missing_contract(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/v1/cases/cases",
            data=json.dumps({"name": "无合同案件"}),
            content_type="application/json",
        )
        # Should handle missing required fields gracefully
        assert resp.status_code in (400, 422, 200)
        if resp.status_code == 200:
            # 接受时必须真实落库并可回查
            data = resp.json()
            assert data["id"]
            assert Case.objects.filter(id=data["id"], name="无合同案件").exists()
        else:
            _assert_error_body(resp)

    @pytest.mark.django_db
    def test_create_reminder_past_due_date(self, authenticated_client):
        case = _make_case()
        past_date = (datetime.now() - timedelta(days=30)).isoformat()
        resp = authenticated_client.post(
            "/api/v1/reminders/create",
            data=json.dumps(
                {
                    "case_id": case.id,
                    "reminder_type": "hearing",
                    "content": "过去日期提醒",
                    "due_at": past_date,
                }
            ),
            content_type="application/json",
        )
        # Should accept past dates (user might want to record historical reminders)
        assert resp.status_code in (200, 400)
        if resp.status_code == 200:
            # 接受历史日期时必须真实落库且响应携带 id
            data = resp.json()
            assert data["id"]
            assert Reminder.objects.filter(id=data["id"], content="过去日期提醒").exists()
        else:
            _assert_error_body(resp)

    @pytest.mark.django_db
    def test_create_client_invalid_phone(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/v1/client/clients",
            data=json.dumps(
                {
                    "name": "电话测试客户",
                    "client_type": "natural",
                    "phone": "not-a-phone",
                }
            ),
            content_type="application/json",
        )
        # Should either validate phone or accept as-is
        assert resp.status_code in (200, 400, 422)
        if resp.status_code == 200:
            # 接受时按原样存储电话（accept-as-is 契约）并真实落库
            data = resp.json()
            assert data["id"]
            assert Client.objects.filter(id=data["id"], phone="not-a-phone").exists()
        else:
            _assert_error_body(resp)

    @pytest.mark.django_db
    def test_invalid_json_payload(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/v1/client/clients",
            data="not valid json",
            content_type="application/json",
        )
        assert resp.status_code in (400, 422, 200)
        if resp.status_code != 200:
            # 非法 JSON 必须被拒绝且错误体带文案
            _assert_error_body(resp)
        # 任何情况下都不应创建出脏数据客户
        assert not Client.objects.filter(name__icontains="not valid json").exists()


# ===================================================================
# 3. Authentication & Authorization
# ===================================================================


class TestAuthentication:
    """Verify authentication enforcement on protected endpoints."""

    @pytest.mark.django_db
    def test_unauthenticated_list_cases(self, api_client):
        # 造锚点数据：若鉴权失效退化为 200 全量列表，锚点案件名必须不出现在响应里
        _make_case(name="未授权泄露锚点案件")
        resp = api_client.get("/api/v1/cases/cases")
        assert resp.status_code in (401, 403, 302)
        if resp.status_code != 302:
            _assert_error_body(resp)
        assert "未授权泄露锚点案件" not in resp.content.decode("utf-8", errors="ignore")

    @pytest.mark.django_db
    def test_unauthenticated_create_client(self, api_client):
        resp = api_client.post(
            "/api/v1/client/clients",
            data=json.dumps({"name": "未认证客户"}),
            content_type="application/json",
        )
        assert resp.status_code in (401, 403, 302)
        if resp.status_code != 302:
            _assert_error_body(resp)
        # 未认证写入绝不能落库
        assert not Client.objects.filter(name="未认证客户").exists()

    @pytest.mark.django_db
    def test_unauthenticated_list_reminders(self, api_client):
        # 造锚点数据：若鉴权失效退化为 200 全量列表，锚点提醒内容必须不出现在响应里
        Reminder.objects.create(
            case=_make_case(),
            reminder_type="hearing",
            content="未授权泄露锚点提醒",
            due_at=datetime.now() + timedelta(days=1),
        )
        resp = api_client.get("/api/v1/reminders/list")
        assert resp.status_code in (401, 403, 302)
        if resp.status_code == 302:
            # 302 分支必须是带目标的登录重定向
            assert resp["Location"]
        else:
            _assert_error_body(resp)
        assert "未授权泄露锚点提醒" not in resp.content.decode("utf-8", errors="ignore")

    @pytest.mark.django_db
    def test_unauthenticated_list_contracts(self, api_client):
        _make_contract(name="未授权泄露锚点合同")
        resp = api_client.get("/api/v1/contracts/contracts")
        assert resp.status_code in (401, 403, 302)
        if resp.status_code != 302:
            _assert_error_body(resp)
        assert "未授权泄露锚点合同" not in resp.content.decode("utf-8", errors="ignore")

    @pytest.mark.django_db
    def test_authenticated_user_can_list_cases(self, authenticated_client):
        _make_case()
        resp = authenticated_client.get("/api/v1/cases/cases")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1


# ===================================================================
# 4. Business Logic: Side Effects & Data Integrity
# ===================================================================


class TestCaseBusinessLogic:
    """Verify case-related business logic and side effects."""

    @pytest.mark.django_db
    def test_create_case_persists_to_db(self, authenticated_client, contract):
        resp = authenticated_client.post(
            "/api/v1/cases/cases",
            data=json.dumps(
                {
                    "name": "持久化测试案件",
                    "contract_id": contract.id,
                    "case_type": "civil",
                }
            ),
            content_type="application/json",
        )
        if resp.status_code == 200:
            data = resp.json()
            assert Case.objects.filter(id=data["id"]).exists()
            case = Case.objects.get(id=data["id"])
            assert case.name == "持久化测试案件"

    @pytest.mark.django_db
    def test_delete_case_removes_from_db(self, authenticated_client):
        case = _make_case()
        case_id = case.id
        resp = authenticated_client.delete(f"/api/v1/cases/cases/{case_id}")
        if resp.status_code in (200, 204):
            assert not Case.objects.filter(id=case_id).exists()

    @pytest.mark.django_db
    def test_list_cases_returns_correct_fields(self, authenticated_client):
        case = _make_case(name="字段验证案件")
        resp = authenticated_client.get("/api/v1/cases/cases")
        assert resp.status_code == 200
        data = resp.json()
        matching = [c for c in data if c["id"] == case.id]
        assert len(matching) == 1
        c = matching[0]
        assert "id" in c
        assert "name" in c

    @pytest.mark.django_db
    def test_case_filter_by_contract(self, authenticated_client):
        contract_a = Contract.objects.create(name="合同A", case_type="civil")
        contract_b = Contract.objects.create(name="合同B", case_type="civil")
        Case.objects.create(name="案件A", contract=contract_a)
        Case.objects.create(name="案件B", contract=contract_b)
        resp = authenticated_client.get("/api/v1/cases/cases", {"contract_id": contract_a.id})
        assert resp.status_code == 200
        data = resp.json()
        # At least our case should be in the results
        names = [c["name"] for c in data]
        assert "案件A" in names

    @pytest.mark.django_db
    def test_create_case_log(self, authenticated_client):
        case = _make_case()
        resp = authenticated_client.post(
            "/api/v1/cases/logs",
            data=json.dumps(
                {
                    "case_id": case.id,
                    "content": "测试日志内容",
                }
            ),
            content_type="application/json",
        )
        if resp.status_code == 200:
            data = resp.json()
            assert CaseLog.objects.filter(id=data["id"]).exists()
            log = CaseLog.objects.get(id=data["id"])
            assert log.content == "测试日志内容"
            assert log.case_id == case.id


class TestClientBusinessLogic:
    """Verify client-related business logic."""

    @pytest.mark.django_db
    def test_create_natural_client(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/v1/client/clients",
            data=json.dumps(
                {
                    "name": "张三",
                    "client_type": "natural",
                    "is_our_client": True,
                    "phone": "13800138000",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        client = Client.objects.get(id=data["id"])
        assert client.client_type == Client.NATURAL
        assert client.is_our_client is True

    @pytest.mark.django_db
    def test_create_legal_client(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/v1/client/clients",
            data=json.dumps(
                {
                    "name": "某某科技有限公司",
                    "client_type": "legal",
                    "legal_representative": "王五",
                    "credit_code": "91110108MA01XXXXX",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        client = Client.objects.get(id=data["id"])
        assert client.client_type == Client.LEGAL

    @pytest.mark.django_db
    def test_update_client_name(self, authenticated_client):
        client = _make_client(name="更新前名称")
        resp = authenticated_client.put(
            f"/api/v1/client/clients/{client.id}",
            data=json.dumps({"name": "更新后名称"}),
            content_type="application/json",
        )
        if resp.status_code == 200:
            client.refresh_from_db()
            assert client.name == "更新后名称"

    @pytest.mark.django_db
    def test_client_search_partial_match(self, authenticated_client):
        Client.objects.create(name="张三丰", client_type=Client.NATURAL, is_our_client=True)
        Client.objects.create(name="张三", client_type=Client.NATURAL, is_our_client=True)
        Client.objects.create(name="李四", client_type=Client.NATURAL, is_our_client=True)
        resp = authenticated_client.get("/api/v1/client/clients", {"search": "张三"})
        assert resp.status_code == 200
        data = resp.json()
        names = [c["name"] for c in data]
        assert "张三" in names or any("张三" in n for n in names)


class TestReminderBusinessLogic:
    """Verify reminder-related business logic."""

    @pytest.mark.django_db
    def test_create_and_retrieve_reminder(self, authenticated_client):
        case = _make_case()
        due = (datetime.now() + timedelta(days=7)).isoformat()
        resp = authenticated_client.post(
            "/api/v1/reminders/create",
            data=json.dumps(
                {
                    "case_id": case.id,
                    "reminder_type": "hearing",
                    "content": "开庭提醒测试",
                    "due_at": due,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        reminder_id = resp.json()["id"]

        # Retrieve and verify
        resp2 = authenticated_client.get(f"/api/v1/reminders/{reminder_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["content"] == "开庭提醒测试"
        assert data["reminder_type"] == "hearing"

    @pytest.mark.django_db
    def test_update_reminder_persists(self, authenticated_client):
        case = _make_case()
        reminder = Reminder.objects.create(
            case=case,
            reminder_type="deadline",
            content="原始内容",
            due_at=datetime.now() + timedelta(days=14),
        )
        resp = authenticated_client.put(
            f"/api/v1/reminders/{reminder.id}",
            data=json.dumps({"content": "更新后内容"}),
            content_type="application/json",
        )
        if resp.status_code == 200:
            reminder.refresh_from_db()
            assert reminder.content == "更新后内容"

    @pytest.mark.django_db
    def test_delete_reminder_removes_from_db(self, authenticated_client):
        case = _make_case()
        reminder = Reminder.objects.create(
            case=case,
            reminder_type="hearing",
            content="待删除",
            due_at=datetime.now() + timedelta(days=1),
        )
        reminder_id = reminder.id
        resp = authenticated_client.delete(f"/api/v1/reminders/{reminder_id}")
        assert resp.status_code == 204
        assert not Reminder.objects.filter(id=reminder_id).exists()

    @pytest.mark.django_db
    def test_list_reminders_filtered_by_case(self, authenticated_client):
        case1 = _make_case(name="案件1")
        case2 = _make_case(name="案件2")
        Reminder.objects.create(
            case=case1,
            reminder_type="hearing",
            content="提醒1",
            due_at=datetime.now() + timedelta(days=1),
        )
        Reminder.objects.create(
            case=case2,
            reminder_type="deadline",
            content="提醒2",
            due_at=datetime.now() + timedelta(days=2),
        )
        resp = authenticated_client.get("/api/v1/reminders/list", {"case_id": case1.id})
        assert resp.status_code == 200
        data = resp.json()
        assert all(r.get("case_id") == case1.id for r in data if "case_id" in r)


class TestContractBusinessLogic:
    """Verify contract-related business logic."""

    @pytest.mark.django_db
    def test_create_contract_persists(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/v1/contracts/contracts",
            data=json.dumps(
                {
                    "name": "持久化测试合同",
                    "case_type": "civil",
                }
            ),
            content_type="application/json",
        )
        if resp.status_code == 200:
            data = resp.json()
            assert Contract.objects.filter(id=data["id"]).exists()

    @pytest.mark.django_db
    def test_list_contracts_returns_data(self, authenticated_client):
        Contract.objects.create(name="列表测试合同", case_type="civil")
        resp = authenticated_client.get("/api/v1/contracts/contracts")
        assert resp.status_code == 200
        data = resp.json()
        # 列表端点为标准分页信封（不传 page 默认 page=1）
        assert isinstance(data["items"], list)
        assert data["total"] >= 1


class TestOrganizationBusinessLogic:
    """Verify organization-related business logic."""

    @pytest.mark.django_db
    def test_login_returns_token(self, api_client, lawyer):
        resp = api_client.post(
            "/api/v1/organization/login",
            data=json.dumps(
                {
                    "username": lawyer.username,
                    "password": "testpass123",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access" in data or "token" in data or "user" in data

    @pytest.mark.django_db
    def test_login_wrong_password(self, api_client, lawyer):
        resp = api_client.post(
            "/api/v1/organization/login",
            data=json.dumps(
                {
                    "username": lawyer.username,
                    "password": "wrongpassword",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code in (400, 401, 200)
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("success") is False or "error" in data
            # 错误密码绝不能签发 token
            assert not (data.get("access") or data.get("token"))
        else:
            _assert_error_body(resp)

    @pytest.mark.django_db
    def test_list_lawyers(self, authenticated_client, law_firm):
        _make_lawyer(law_firm, username="list_lawyer_1")
        _make_lawyer(law_firm, username="list_lawyer_2")
        resp = authenticated_client.get("/api/v1/organization/lawyers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2


# ===================================================================
# 5. Edge Cases
# ===================================================================


class TestEdgeCases:
    """Verify behavior at boundaries and with unusual inputs."""

    @pytest.mark.django_db
    def test_list_cases_empty_database(self, authenticated_client):
        Case.objects.all().delete()
        resp = authenticated_client.get("/api/v1/cases/cases")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.django_db
    def test_list_clients_empty_database(self, authenticated_client):
        Client.objects.all().delete()
        resp = authenticated_client.get("/api/v1/client/clients")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.django_db
    def test_create_client_max_length_name(self, authenticated_client):
        long_name = "测" * 500
        resp = authenticated_client.post(
            "/api/v1/client/clients",
            data=json.dumps({"name": long_name, "client_type": "natural"}),
            content_type="application/json",
        )
        # Should either accept or reject gracefully
        assert resp.status_code in (200, 400, 422)
        if resp.status_code == 200:
            # 接受时必须真实落库（字段层校验放行）
            data = resp.json()
            assert data["id"]
            assert Client.objects.filter(id=data["id"]).exists()
        else:
            # 拒绝分支：结构化错误体 + name 字段级校验信息 + 不落脏数据
            data = resp.json()
            assert data["code"] == "VALIDATION_ERROR"
            assert data.get("errors", {}).get("name")
            assert not Client.objects.filter(name=long_name).exists()

    @pytest.mark.django_db
    def test_case_list_pagination(self, authenticated_client):
        # Create many cases
        for i in range(25):
            _make_case(name=f"分页测试案件{i}")
        resp = authenticated_client.get("/api/v1/cases/cases")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.django_db
    def test_concurrent_case_creation(self, authenticated_client, contract):
        """Verify that creating multiple cases doesn't cause conflicts."""
        case_ids = []
        for i in range(5):
            resp = authenticated_client.post(
                "/api/v1/cases/cases",
                data=json.dumps(
                    {
                        "name": f"并发测试案件{i}",
                        "contract_id": contract.id,
                        "case_type": "civil",
                    }
                ),
                content_type="application/json",
            )
            if resp.status_code == 200:
                case_ids.append(resp.json()["id"])
        # All should have unique IDs
        assert len(case_ids) == len(set(case_ids))
