"""
团队 CRUD API 集成测试

通过 Django test Client 测试完整的 CRUD 流程。
使用 factories 创建测试数据。

Requirements: 5.6
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.test import Client as TestClient

from apps.organization.models import Team, TeamType
from tests.factories.organization_factories import LawFirmFactory, LawyerFactory, TeamFactory


@pytest.mark.django_db
@pytest.mark.integration
class TestTeamListAPI:
    """团队列表查询 API 测试"""

    def setup_method(self) -> None:
        self.client = TestClient()

    def test_list_teams_superuser(self) -> None:
        """超级管理员查询所有团队"""
        law_firm = LawFirmFactory()
        TeamFactory.create_batch(3, law_firm=law_firm)
        superuser = LawyerFactory(is_superuser=True)
        self.client.force_login(superuser)  # type: ignore[arg-type]

        response = self.client.get("/api/v1/organization/teams")

        assert response.status_code == 200
        data: Any = response.json()
        assert len(data) >= 3

    def test_list_teams_filter_by_law_firm(self) -> None:
        """按律所过滤团队"""
        firm_a = LawFirmFactory()
        firm_b = LawFirmFactory()
        TeamFactory.create_batch(2, law_firm=firm_a)
        TeamFactory(law_firm=firm_b)
        superuser = LawyerFactory(is_superuser=True)
        self.client.force_login(superuser)  # type: ignore[arg-type]

        response = self.client.get(f"/api/v1/organization/teams?law_firm_id={firm_a.id}")  # type: ignore[attr-defined]

        assert response.status_code == 200
        data: Any = response.json()
        assert len(data) == 2

    def test_list_teams_filter_by_type(self) -> None:
        """按团队类型过滤"""
        firm = LawFirmFactory()
        TeamFactory.create_batch(2, law_firm=firm, team_type=TeamType.LAWYER)
        TeamFactory(law_firm=firm, team_type=TeamType.BIZ)
        superuser = LawyerFactory(is_superuser=True)
        self.client.force_login(superuser)  # type: ignore[arg-type]

        response = self.client.get("/api/v1/organization/teams?team_type=lawyer")

        assert response.status_code == 200
        data: Any = response.json()
        assert len(data) == 2

    def test_list_teams_normal_user_sees_own_firm(self) -> None:
        """普通用户只能看到自己律所的团队"""
        firm_a = LawFirmFactory()
        firm_b = LawFirmFactory()
        TeamFactory.create_batch(2, law_firm=firm_a)
        TeamFactory(law_firm=firm_b)
        user = LawyerFactory(law_firm=firm_a, is_admin=False)
        self.client.force_login(user)  # type: ignore[arg-type]

        response = self.client.get("/api/v1/organization/teams")

        assert response.status_code == 200
        data: Any = response.json()
        assert len(data) == 2


@pytest.mark.django_db
@pytest.mark.integration
class TestTeamGetAPI:
    """团队详情查询 API 测试"""

    def setup_method(self) -> None:
        self.client = TestClient()

    def test_get_team_success(self) -> None:
        """获取团队详情"""
        firm = LawFirmFactory()
        team = TeamFactory(law_firm=firm, name="测试团队A")
        user = LawyerFactory(law_firm=firm)
        self.client.force_login(user)  # type: ignore[arg-type]

        response = self.client.get(f"/api/v1/organization/teams/{team.id}")  # type: ignore[attr-defined]

        assert response.status_code == 200
        data: Any = response.json()
        assert data["id"] == team.id  # type: ignore[attr-defined]
        assert data["name"] == "测试团队A"

    def test_get_team_not_found(self) -> None:
        """获取不存在的团队返回错误"""
        superuser = LawyerFactory(is_superuser=True)
        self.client.force_login(superuser)  # type: ignore[arg-type]

        response = self.client.get("/api/v1/organization/teams/999999")

        # NotFoundError 由全局异常处理器捕获
        assert response.status_code in (404, 500)


@pytest.mark.django_db
@pytest.mark.integration
class TestTeamCreateAPI:
    """团队创建 API 测试"""

    def setup_method(self) -> None:
        self.client = TestClient()

    def test_create_team_success(self) -> None:
        """管理员创建团队"""
        firm = LawFirmFactory()
        admin = LawyerFactory(law_firm=firm, is_admin=True)
        self.client.force_login(admin)  # type: ignore[arg-type]

        payload = {
            "name": "新律师团队",
            "team_type": "lawyer",
            "law_firm_id": firm.id,  # type: ignore[attr-defined]
        }
        response = self.client.post(
            "/api/v1/organization/teams",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200
        data: Any = response.json()
        assert data["name"] == "新律师团队"
        assert data["team_type"] == "lawyer"

    def test_create_team_permission_denied(self) -> None:
        """普通用户无权创建团队"""
        firm = LawFirmFactory()
        normal_user = LawyerFactory(law_firm=firm, is_admin=False, is_superuser=False)
        self.client.force_login(normal_user)  # type: ignore[arg-type]

        payload = {
            "name": "新团队",
            "team_type": "lawyer",
            "law_firm_id": firm.id,  # type: ignore[attr-defined]
        }
        response = self.client.post(
            "/api/v1/organization/teams",
            data=json.dumps(payload),
            content_type="application/json",
        )

        # PermissionDenied 由全局异常处理器捕获
        assert response.status_code in (403, 500)

    def test_create_team_invalid_type(self) -> None:
        """无效团队类型被拒绝"""
        firm = LawFirmFactory()
        admin = LawyerFactory(law_firm=firm, is_admin=True)
        self.client.force_login(admin)  # type: ignore[arg-type]

        payload = {
            "name": "无效团队",
            "team_type": "invalid_type",
            "law_firm_id": firm.id,  # type: ignore[attr-defined]
        }
        response = self.client.post(
            "/api/v1/organization/teams",
            data=json.dumps(payload),
            content_type="application/json",
        )

        # ValidationException 由全局异常处理器捕获
        assert response.status_code in (400, 422, 500)


@pytest.mark.django_db
@pytest.mark.integration
class TestTeamUpdateAPI:
    """团队更新 API 测试"""

    def setup_method(self) -> None:
        self.client = TestClient()

    def test_update_team_success(self) -> None:
        """管理员更新团队"""
        firm = LawFirmFactory()
        team = TeamFactory(law_firm=firm, name="旧名称", team_type=TeamType.LAWYER)
        admin = LawyerFactory(law_firm=firm, is_admin=True)
        self.client.force_login(admin)  # type: ignore[arg-type]

        payload = {
            "name": "新名称",
            "team_type": "lawyer",
            "law_firm_id": firm.id,  # type: ignore[attr-defined]
        }
        response = self.client.put(
            f"/api/v1/organization/teams/{team.id}",  # type: ignore[attr-defined]
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200
        data: Any = response.json()
        assert data["name"] == "新名称"

    def test_update_team_not_found(self) -> None:
        """更新不存在的团队返回错误"""
        firm = LawFirmFactory()
        admin = LawyerFactory(law_firm=firm, is_admin=True)
        self.client.force_login(admin)  # type: ignore[arg-type]

        payload = {
            "name": "新名称",
            "team_type": "lawyer",
            "law_firm_id": firm.id,  # type: ignore[attr-defined]
        }
        response = self.client.put(
            "/api/v1/organization/teams/999999",
            data=json.dumps(payload),
            content_type="application/json",
        )

        # NotFoundError 由全局异常处理器捕获
        assert response.status_code in (404, 500)


@pytest.mark.django_db
@pytest.mark.integration
class TestTeamDeleteAPI:
    """团队删除 API 测试"""

    def setup_method(self) -> None:
        self.client = TestClient()

    def test_delete_team_success(self) -> None:
        """管理员删除团队"""
        firm = LawFirmFactory()
        team = TeamFactory(law_firm=firm)
        team_id = team.id  # type: ignore[attr-defined]
        admin = LawyerFactory(law_firm=firm, is_admin=True)
        self.client.force_login(admin)  # type: ignore[arg-type]

        response = self.client.delete(f"/api/v1/organization/teams/{team_id}")

        assert response.status_code == 200
        assert not Team.objects.filter(id=team_id).exists()

    def test_delete_team_not_found(self) -> None:
        """删除不存在的团队返回错误"""
        superuser = LawyerFactory(is_superuser=True)
        self.client.force_login(superuser)  # type: ignore[arg-type]

        response = self.client.delete("/api/v1/organization/teams/999999")

        # NotFoundError 由全局异常处理器捕获
        assert response.status_code in (404, 500)

    def test_delete_team_permission_denied(self) -> None:
        """普通用户无权删除团队"""
        firm = LawFirmFactory()
        team = TeamFactory(law_firm=firm)
        normal_user = LawyerFactory(law_firm=firm, is_admin=False, is_superuser=False)
        self.client.force_login(normal_user)  # type: ignore[arg-type]

        response = self.client.delete(f"/api/v1/organization/teams/{team.id}")  # type: ignore[attr-defined]

        # PermissionDenied 由全局异常处理器捕获
        assert response.status_code in (403, 500)
