"""系统配置 CRUD 端到端测试（branch: refactor/core-cleanup）。

验证本分支核心改动：``apps/core/api/__init__.py`` 从直连 ``SystemConfigRepository``
改为走 ``SystemConfigService``（四层架构修复），以及配套的 Service/Repository 方法新增。

覆盖场景：
1. **API 层全链路（最重要）**：用 Ninja ``TestClient`` 打真实 ``/api/v1/config/system-configs``
   路由（带已认证用户，走完整 auth → schema 校验 → service → repo → DB 链路），验证 5 个端点：
   - ``GET`` 返回分组结构（groups/category/items），secret 值掩码为 ``******``
   - ``PUT`` 批量更新（更新已有 key + 创建新 key 两条路径）
   - ``POST`` 创建（成功 + 409 冲突）
   - ``PATCH /{key}`` 更新（成功 + 404）
   - ``DELETE /{key}`` 删除（成功 + 404）
   - 未认证访问返回 401（auth 仍生效，回归保护）
2. **Service 层行为**：``get_all_active_configs()`` 只返回 ``is_active=True``；
   ``get_config_by_key()`` 存在返回实例、不存在返回 None（不抛异常）。
3. **``aget_value`` 走 repo 后的语义**：存在的 key 返回值、不存在返回默认值、
   ``is_active=False`` 被忽略（``aget_active_by_key`` 的关键语义）。
4. **掩码逻辑**：``is_secret=True`` 在 list 返回 ``******`` 且 ``has_value`` 仍为 True；
   ``is_secret=False`` 且值为空时 ``has_value=False``。
5. **架构回归**：``apps.core.api`` 模块不再持有 ``SystemConfigRepository`` 引用；
   原有 mock service 的 ``tests/ci/unit/core/test_core_api_init.py`` 保持兼容。

运行方式（postgres 测试库）::

    cd backend
    TEST_DB_NAME=fachuan_ci_test DB_ENGINE=postgresql DB_NAME=fachuan_ci_test \\
        DB_USER=postgres DB_PASSWORD=postgres PYTHONPATH=apiSystem:. \\
    .venv/bin/pytest tests/ci/unit/core/test_e2e_system_config_branch.py \\
        --no-header -p no:cacheprovider -p no:warnings --tb=short -q \\
        --reuse-db --timeout=300
"""

from __future__ import annotations

from typing import Any

import pytest
from asgiref.sync import async_to_sync

from apps.core.models.system_config import SystemConfig

# ── 常量 ──────────────────────────────────────────────────────────────────────

CONFIG_PREFIX = "/config/system-configs"  # api_v1 挂载前缀 + router 内路径


# ── Fixtures / Helpers ───────────────────────────────────────────────────────


def _create_admin_user() -> Any:
    """创建一个已认证的管理员律师（用于 TestClient 的 user 参数）。"""
    from apps.organization.models import LawFirm, Lawyer

    firm = LawFirm.objects.create(name=f"系统配置E2E律所-{Lawyer.objects.count()}")
    return Lawyer.objects.create_user(
        username=f"e2e_sysconfig_{Lawyer.objects.count()}",
        password="testpass123",  # pragma: allowlist secret
        is_admin=True,
        is_superuser=True,
        law_firm=firm,
    )


@pytest.fixture
def api_client() -> Any:
    """打真实 api_v1 路由的 Ninja TestClient。"""
    from ninja.testing import TestClient

    from apiSystem.api import api_v1

    return TestClient(api_v1)


@pytest.fixture
def authed_user() -> Any:
    """已认证管理员用户。"""
    return _create_admin_user()


def _seed(key: str, **kwargs: Any) -> Any:
    """直接造一条 SystemConfig 数据。"""
    from apps.core.models.system_config import SystemConfig

    return SystemConfig.objects.create(key=key, **kwargs)


def _list_keys(response_json: dict[str, Any]) -> set[str]:
    """从 list 响应中提取全部 key。"""
    return {item["key"] for group in response_json["groups"] for item in group["items"]}


def _find_item(response_json: dict[str, Any], key: str) -> dict[str, Any] | None:
    """从 list 响应中按 key 找 item。"""
    for group in response_json["groups"]:
        for item in group["items"]:
            if item["key"] == key:
                found: dict[str, Any] = item
                return found
    return None


# =====================================================================
# 场景 1: API 层全链路（最重要）
# =====================================================================


@pytest.mark.django_db
class TestApiLayerFullChain:
    """通过 Ninja TestClient 打真实 HTTP 路由，验证 5 个端点的完整链路。"""

    # ── GET /system-configs ──────────────────────────────────────────────

    def test_get_returns_grouped_structure(self, api_client: Any, authed_user: Any) -> None:
        """GET 返回 groups/category/items 分组结构，仅含 is_active=True 的配置。"""
        _seed("E2E_G_KEY_A", value="va", category="general", is_active=True)
        _seed("E2E_G_KEY_B", value="vb", category="general", is_active=True)
        _seed("E2E_G_INACTIVE", value="vc", category="general", is_active=False)

        response = api_client.get(CONFIG_PREFIX, user=authed_user)

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["groups"], list)
        assert len(body["groups"]) >= 1

        keys = _list_keys(body)
        assert "E2E_G_KEY_A" in keys
        assert "E2E_G_KEY_B" in keys
        # 回归保护：is_active=False 不得出现在 list 结果中
        assert "E2E_G_INACTIVE" not in keys

        # 分组结构：category 字段存在，且 group.items 里每项都带全字段
        for group in body["groups"]:
            assert "category" in group
            assert "items" in group
            for item in group["items"]:
                assert item["category"] == group["category"]
                for field in ("key", "value", "description", "is_secret", "is_active", "has_value"):
                    assert field in item

    def test_get_groups_separate_categories(self, api_client: Any, authed_user: Any) -> None:
        """不同 category 的配置被分到不同 group。"""
        _seed("E2E_CAT_A", value="x", category="general", is_active=True)
        _seed("E2E_CAT_B", value="y", category="ocr", is_active=True)

        body = api_client.get(CONFIG_PREFIX, user=authed_user).json()

        categories = {group["category"] for group in body["groups"]}
        assert "general" in categories
        assert "ocr" in categories

        item_a = _find_item(body, "E2E_CAT_A")
        item_b = _find_item(body, "E2E_CAT_B")
        assert item_a is not None and item_a["category"] == "general"
        assert item_b is not None and item_b["category"] == "ocr"

    def test_get_masks_secret_value(self, api_client: Any, authed_user: Any) -> None:
        """is_secret=True 的配置在 list 中 value 被掩码为 '******'，且 has_value 为 True。"""
        _seed("E2E_SECRET_KEY", value="real-secret-value", category="general", is_secret=True, is_active=True)

        body = api_client.get(CONFIG_PREFIX, user=authed_user).json()

        item = _find_item(body, "E2E_SECRET_KEY")
        assert item is not None
        assert item["value"] == "******"
        assert item["is_secret"] is True
        # 掩码不等于泄露：真实值不出现在响应里
        assert "real-secret-value" not in response_text(body)
        # 有值时 has_value 仍为 True（掩码不影响有值判断）
        assert item["has_value"] is True

    def test_get_non_secret_empty_value_has_value_false(self, api_client: Any, authed_user: Any) -> None:
        """is_secret=False 且值为空时 has_value=False。"""
        _seed("E2E_EMPTY_KEY", value="", category="general", is_secret=False, is_active=True)

        body = api_client.get(CONFIG_PREFIX, user=authed_user).json()

        item = _find_item(body, "E2E_EMPTY_KEY")
        assert item is not None
        assert item["value"] == ""
        assert item["is_secret"] is False
        assert item["has_value"] is False

    def test_get_unauthenticated_returns_401(self, api_client: Any) -> None:
        """未认证访问被 JWTOrSessionAuth 拦截，返回 401。"""
        response = api_client.get(CONFIG_PREFIX)
        assert response.status_code == 401

    # ── PUT /system-configs ──────────────────────────────────────────────

    def test_put_updates_existing_key(self, api_client: Any, authed_user: Any) -> None:
        """PUT 更新已有 key 的值，updated_count 正确，DB 值真实变更。"""
        _seed("E2E_PUT_EXISTING", value="old-value", category="general", is_active=True)

        response = api_client.put(
            CONFIG_PREFIX,
            json={"category": "general", "updates": {"E2E_PUT_EXISTING": "new-value"}},
            user=authed_user,
        )

        assert response.status_code == 200
        assert response.json() == {"success": True, "updated_count": 1}

        from apps.core.models.system_config import SystemConfig

        assert SystemConfig.objects.get(key="E2E_PUT_EXISTING").value == "new-value"

    def test_put_creates_missing_key(self, api_client: Any, authed_user: Any) -> None:
        """PUT 对不存在的 key 自动创建，使用 payload.category 且默认非敏感。"""
        response = api_client.put(
            CONFIG_PREFIX,
            json={"category": "ocr", "updates": {"E2E_PUT_BRAND_NEW": "fresh"}},
            user=authed_user,
        )

        assert response.status_code == 200
        assert response.json() == {"success": True, "updated_count": 1}

        from apps.core.models.system_config import SystemConfig

        created = SystemConfig.objects.get(key="E2E_PUT_BRAND_NEW")
        assert created.value == "fresh"
        assert created.category == "ocr"
        assert created.is_secret is False
        assert created.is_active is True

    def test_put_mixed_existing_and_new(self, api_client: Any, authed_user: Any) -> None:
        """PUT 一次同时命中「更新已有」和「创建新」两条路径，updated_count 为条目总数。"""
        _seed("E2E_PUT_MIX_OLD", value="v0", category="general", is_active=True)

        response = api_client.put(
            CONFIG_PREFIX,
            json={"category": "general", "updates": {"E2E_PUT_MIX_OLD": "v1", "E2E_PUT_MIX_NEW": "v2"}},
            user=authed_user,
        )

        assert response.status_code == 200
        assert response.json()["updated_count"] == 2

        from apps.core.models.system_config import SystemConfig

        assert SystemConfig.objects.get(key="E2E_PUT_MIX_OLD").value == "v1"
        assert SystemConfig.objects.get(key="E2E_PUT_MIX_NEW").value == "v2"

    def test_put_revives_inactive_config(self, api_client: Any, authed_user: Any) -> None:
        """PUT 命中已存在但 is_active=False 的 key 时，会把它重新置为启用并出现在 list 中。"""
        _seed("E2E_PUT_INACTIVE", value="stale", category="general", is_active=False)

        response = api_client.put(
            CONFIG_PREFIX,
            json={"category": "general", "updates": {"E2E_PUT_INACTIVE": "revived"}},
            user=authed_user,
        )

        assert response.status_code == 200
        from apps.core.models.system_config import SystemConfig

        revived = SystemConfig.objects.get(key="E2E_PUT_INACTIVE")
        assert revived.is_active is True
        assert revived.value == "revived"
        assert "E2E_PUT_INACTIVE" in _list_keys(api_client.get(CONFIG_PREFIX, user=authed_user).json())

    # ── POST /system-configs ─────────────────────────────────────────────

    def test_post_creates_new_config(self, api_client: Any, authed_user: Any) -> None:
        """POST 创建新配置项，返回完整 item 且落库。"""
        response = api_client.post(
            CONFIG_PREFIX,
            json={"key": "E2E_POST_NEW", "value": "created", "category": "general", "description": "描述"},
            user=authed_user,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["key"] == "E2E_POST_NEW"
        assert body["value"] == "created"
        assert body["category"] == "general"
        assert body["description"] == "描述"
        assert body["is_secret"] is False
        assert body["is_active"] is True
        assert body["has_value"] is True

        from apps.core.models.system_config import SystemConfig

        assert SystemConfig.objects.filter(key="E2E_POST_NEW").exists()

    def test_post_duplicate_key_returns_409(self, api_client: Any, authed_user: Any) -> None:
        """POST 已存在的 key 返回 409 冲突，且不修改原值。"""
        _seed("E2E_POST_DUP", value="original", category="general", is_active=True)

        response = api_client.post(
            CONFIG_PREFIX,
            json={"key": "E2E_POST_DUP", "value": "attempted-overwrite"},
            user=authed_user,
        )

        assert response.status_code == 409
        assert "E2E_POST_DUP" in response.json()["message"]

        from apps.core.models.system_config import SystemConfig

        assert SystemConfig.objects.get(key="E2E_POST_DUP").value == "original"

    def test_post_secret_config_masks_value(self, api_client: Any, authed_user: Any) -> None:
        """POST is_secret=True 时响应 value 掩码，DB 中密文存储（非明文）。"""
        response = api_client.post(
            CONFIG_PREFIX,
            json={"key": "E2E_POST_SECRET", "value": "top-secret-plain", "is_secret": True},
            user=authed_user,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["value"] == "******"
        assert body["is_secret"] is True
        assert body["has_value"] is True

        from apps.core.models.system_config import SystemConfig

        stored = SystemConfig.objects.get(key="E2E_POST_SECRET").value
        assert stored != "top-secret-plain"  # 不明文落库
        assert "top-secret-plain" not in response_text(body)

    # ── PATCH /system-configs/{key} ──────────────────────────────────────

    def test_patch_updates_value(self, api_client: Any, authed_user: Any) -> None:
        """PATCH 更新单个配置项的值，返回更新后的 item。"""
        _seed("E2E_PATCH_TARGET", value="before", category="general", is_active=True)

        response = api_client.patch(
            f"{CONFIG_PREFIX}/E2E_PATCH_TARGET",
            json={"value": "after"},
            user=authed_user,
        )

        assert response.status_code == 200
        assert response.json()["value"] == "after"
        from apps.core.models.system_config import SystemConfig

        assert SystemConfig.objects.get(key="E2E_PATCH_TARGET").value == "after"

    def test_patch_updates_metadata_fields(self, api_client: Any, authed_user: Any) -> None:
        """PATCH 可同时更新 category / description / is_secret / is_active。"""
        _seed("E2E_PATCH_META", value="v", category="general", description="旧", is_active=True)

        response = api_client.patch(
            f"{CONFIG_PREFIX}/E2E_PATCH_META",
            json={"category": "ocr", "description": "新描述", "is_secret": True, "is_active": False},
            user=authed_user,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["category"] == "ocr"
        assert body["description"] == "新描述"
        assert body["is_secret"] is True
        assert body["is_active"] is False

        from apps.core.models.system_config import SystemConfig

        cfg = SystemConfig.objects.get(key="E2E_PATCH_META")
        assert cfg.category == "ocr"
        assert cfg.description == "新描述"
        assert cfg.is_secret is True
        assert cfg.is_active is False

    def test_patch_missing_key_returns_404(self, api_client: Any, authed_user: Any) -> None:
        """PATCH 不存在的 key 返回 404。"""
        response = api_client.patch(
            f"{CONFIG_PREFIX}/E2E_PATCH_NOPE",
            json={"value": "x"},
            user=authed_user,
        )

        assert response.status_code == 404
        assert "E2E_PATCH_NOPE" in response.json()["message"]

    # ── DELETE /system-configs/{key} ─────────────────────────────────────

    def test_delete_removes_config(self, api_client: Any, authed_user: Any) -> None:
        """DELETE 删除已存在的配置项，返回 success 且 DB 记录消失。"""
        _seed("E2E_DEL_TARGET", value="v", category="general", is_active=True)

        response = api_client.delete(f"{CONFIG_PREFIX}/E2E_DEL_TARGET", user=authed_user)

        assert response.status_code == 200
        assert response.json() == {"success": True}

        from apps.core.models.system_config import SystemConfig

        assert not SystemConfig.objects.filter(key="E2E_DEL_TARGET").exists()

    def test_delete_missing_key_returns_404(self, api_client: Any, authed_user: Any) -> None:
        """DELETE 不存在的 key 返回 404。"""
        response = api_client.delete(f"{CONFIG_PREFIX}/E2E_DEL_NOPE", user=authed_user)

        assert response.status_code == 404
        assert "E2E_DEL_NOPE" in response.json()["message"]

    # ── 端到端 CRUD 组合 ─────────────────────────────────────────────────

    def test_full_crud_lifecycle(self, api_client: Any, authed_user: Any) -> None:
        """一条完整链路：POST 创建 → GET 可见 → PUT 改值 → PATCH 改属性 → DELETE 删除 → GET 不可见。"""
        # 1. 创建
        created = api_client.post(
            CONFIG_PREFIX,
            json={"key": "E2E_LIFECYCLE", "value": "step1", "category": "general"},
            user=authed_user,
        )
        assert created.status_code == 200
        assert created.json()["key"] == "E2E_LIFECYCLE"

        # 2. list 可见
        assert "E2E_LIFECYCLE" in _list_keys(api_client.get(CONFIG_PREFIX, user=authed_user).json())

        # 3. PUT 改值
        put = api_client.put(
            CONFIG_PREFIX,
            json={"category": "general", "updates": {"E2E_LIFECYCLE": "step2"}},
            user=authed_user,
        )
        assert put.status_code == 200
        assert put.json()["updated_count"] == 1

        # 4. PATCH 改属性
        patched = api_client.patch(
            f"{CONFIG_PREFIX}/E2E_LIFECYCLE",
            json={"description": "生命周期描述", "is_secret": True},
            user=authed_user,
        )
        assert patched.status_code == 200
        assert patched.json()["description"] == "生命周期描述"
        assert patched.json()["is_secret"] is True

        # 5. DELETE 删除
        deleted = api_client.delete(f"{CONFIG_PREFIX}/E2E_LIFECYCLE", user=authed_user)
        assert deleted.status_code == 200
        assert deleted.json()["success"] is True

        # 6. list 不再可见
        assert "E2E_LIFECYCLE" not in _list_keys(api_client.get(CONFIG_PREFIX, user=authed_user).json())


def response_text(body: Any) -> str:
    """把响应体序列化成字符串，用于「真实值未泄露」断言。"""
    import json

    return json.dumps(body, ensure_ascii=False, default=str)


# =====================================================================
# 场景 2: Service 层行为
# =====================================================================


@pytest.mark.django_db
class TestServiceLayerBehavior:
    """验证 SystemConfigService 新增方法的真实行为（走 repo → DB）。"""

    def test_get_all_active_configs_returns_only_active(self) -> None:
        """get_all_active_configs() 只返回 is_active=True 的配置。"""
        from apps.core.services.system_config_service import SystemConfigService

        _seed("E2E_SVC_ACTIVE_1", value="a", category="general", is_active=True)
        _seed("E2E_SVC_ACTIVE_2", value="b", category="ocr", is_active=True)
        _seed("E2E_SVC_INACTIVE", value="c", category="general", is_active=False)

        result = SystemConfigService().get_all_active_configs()

        keys = {cfg.key for cfg in result}
        assert "E2E_SVC_ACTIVE_1" in keys
        assert "E2E_SVC_ACTIVE_2" in keys
        assert "E2E_SVC_INACTIVE" not in keys
        # 全部返回项都是启用的
        assert all(cfg.is_active for cfg in result)

    def test_get_all_active_configs_returns_model_instances(self) -> None:
        """get_all_active_configs() 返回 SystemConfig 模型实例（带元数据字段）。"""
        from apps.core.models.system_config import SystemConfig
        from apps.core.services.system_config_service import SystemConfigService

        _seed("E2E_SVC_INSTANCE", value="v", category="general", is_secret=True, is_active=True)

        result = SystemConfigService().get_all_active_configs()
        matched = [cfg for cfg in result if cfg.key == "E2E_SVC_INSTANCE"]

        assert len(matched) == 1
        assert isinstance(matched[0], SystemConfig)
        assert matched[0].is_secret is True
        assert matched[0].category == "general"

    def test_get_config_by_key_returns_instance_with_metadata(self) -> None:
        """get_config_by_key() 对存在的 key 返回模型实例（含 is_secret 等元数据）。"""
        from apps.core.models.system_config import SystemConfig
        from apps.core.services.system_config_service import SystemConfigService

        _seed("E2E_SVC_BYKEY", value="secret", category="email", is_secret=True, description="邮箱密钥")

        config = SystemConfigService().get_config_by_key("E2E_SVC_BYKEY")

        assert config is not None
        assert isinstance(config, SystemConfig)
        assert config.key == "E2E_SVC_BYKEY"
        assert config.is_secret is True
        assert config.category == "email"
        assert config.description == "邮箱密钥"

    def test_get_config_by_key_returns_none_for_missing(self) -> None:
        """get_config_by_key() 对不存在的 key 返回 None 而不抛异常。"""
        from apps.core.services.system_config_service import SystemConfigService

        result = SystemConfigService().get_config_by_key("E2E_SVC_TOTALLY_ABSENT")

        assert result is None

    def test_get_config_by_key_finds_inactive_config(self) -> None:
        """get_config_by_key() 不按 is_active 过滤（存在性判断用途），能找到停用的配置。"""
        from apps.core.services.system_config_service import SystemConfigService

        _seed("E2E_SVC_INACTIVE_BYKEY", value="v", category="general", is_active=False)

        config = SystemConfigService().get_config_by_key("E2E_SVC_INACTIVE_BYKEY")

        assert config is not None
        assert config.is_active is False

    def test_set_value_encrypts_secret_at_rest(self) -> None:
        """set_value(is_secret=True) 落库为密文，get_value 读回明文。"""
        from django.core.cache import cache

        from apps.core.models.system_config import SystemConfig
        from apps.core.services.system_config_service import SystemConfigService

        service = SystemConfigService(cache_timeout=60)
        service.set_value(key="E2E_SVC_SECRET_AT_REST", value="plain-text", is_secret=True)
        cache.delete("system_config:E2E_SVC_SECRET_AT_REST")

        stored = SystemConfig.objects.get(key="E2E_SVC_SECRET_AT_REST").value
        assert stored != "plain-text"
        assert stored.startswith("enc:v1:")
        assert service.get_value("E2E_SVC_SECRET_AT_REST") == "plain-text"


# =====================================================================
# 场景 3: aget_value 走 repo 后的行为
# =====================================================================


@pytest.mark.django_db
class TestAGetValueViaRepository:
    """验证 aget_value 改走 SystemConfigRepository.aget_active_by_key 后的语义。

    用 ``async_to_sync`` 驱动 async ORM，而非 ``transaction=True`` + ``pytest.mark.asyncio``：
    TransactionTestCase 的 teardown flush 会与 post-migrate 的 create_permissions 竞争，
    在本机共享开发库上间歇触发 auth_permission 唯一约束冲突（既存基础设施抖动，
    与用例本身无关）。plain ``django_db`` 走事务回滚，无此问题。
    """

    def test_returns_value_for_existing_key(self) -> None:
        """存在的 key 返回值。"""
        from apps.core.services.system_config_service import SystemConfigService

        async def _run() -> str:
            await SystemConfig.objects.acreate(key="E2E_AGET_PRESENT", value="async-val", is_active=True)
            return await SystemConfigService.aget_value("E2E_AGET_PRESENT")

        assert async_to_sync(_run)() == "async-val"

    def test_returns_default_for_missing_key(self) -> None:
        """不存在的 key 返回默认值。"""
        from apps.core.services.system_config_service import SystemConfigService

        assert async_to_sync(SystemConfigService.aget_value)("E2E_AGET_ABSENT", "fallback") == "fallback"

    def test_ignores_inactive_configs(self) -> None:
        """is_active=False 的配置被忽略，返回默认值（aget_active_by_key 的关键语义）。"""
        from apps.core.services.system_config_service import SystemConfigService

        async def _run() -> str:
            await SystemConfig.objects.acreate(key="E2E_AGET_INACTIVE", value="hidden", is_active=False)
            return await SystemConfigService.aget_value("E2E_AGET_INACTIVE", "default-wins")

        assert async_to_sync(_run)() == "default-wins"

    def test_returns_empty_default_when_absent(self) -> None:
        """不存在的 key 且未传默认值时返回空串。"""
        from apps.core.services.system_config_service import SystemConfigService

        assert async_to_sync(SystemConfigService.aget_value)("E2E_AGET_NO_DEFAULT") == ""

    def test_secret_value_is_decrypted(self) -> None:
        """is_secret=True 的配置经 aget_value 读回解密后的明文。"""
        from apps.core.services.system_config_service import SystemConfigService

        async def _run() -> str:
            await SystemConfig.objects.acreate(
                key="E2E_AGET_SECRET", value="plain-secret", is_secret=True, is_active=True
            )
            return await SystemConfigService.aget_value("E2E_AGET_SECRET")

        assert async_to_sync(_run)() == "plain-secret"


# =====================================================================
# 场景 4: 掩码逻辑（API 层 secret 语义集中验证）
# =====================================================================


@pytest.mark.django_db
class TestMaskingLogic:
    """掩码与 has_value 的交叉语义。"""

    def test_secret_with_value_masked_and_has_value_true(self, api_client: Any, authed_user: Any) -> None:
        """is_secret=True 有值：value='******'、has_value=True。"""
        _seed("E2E_MASK_SECRET_FULL", value="hidden-token", is_secret=True, is_active=True)

        item = _find_item(api_client.get(CONFIG_PREFIX, user=authed_user).json(), "E2E_MASK_SECRET_FULL")

        assert item is not None
        assert item["value"] == "******"
        assert item["has_value"] is True

    def test_non_secret_with_value_shown(self, api_client: Any, authed_user: Any) -> None:
        """is_secret=False 有值：value 原样返回、has_value=True。"""
        _seed("E2E_MASK_PLAIN_FULL", value="visible-token", is_secret=False, is_active=True)

        item = _find_item(api_client.get(CONFIG_PREFIX, user=authed_user).json(), "E2E_MASK_PLAIN_FULL")

        assert item is not None
        assert item["value"] == "visible-token"
        assert item["has_value"] is True

    def test_secret_without_value_still_masked(self, api_client: Any, authed_user: Any) -> None:
        """is_secret=True 无值：value 仍为 '******'（掩码优先于空值判断）。"""
        _seed("E2E_MASK_SECRET_EMPTY", value="", is_secret=True, is_active=True)

        item = _find_item(api_client.get(CONFIG_PREFIX, user=authed_user).json(), "E2E_MASK_SECRET_EMPTY")

        assert item is not None
        assert item["value"] == "******"
        assert item["has_value"] is False

    def test_no_plaintext_secret_leaks_in_list(self, api_client: Any, authed_user: Any) -> None:
        """list 响应整体不含任何 secret 配置的明文值。"""
        _seed("E2E_MASK_LEAK_A", value="super-secret-alpha", is_secret=True, is_active=True)
        _seed("E2E_MASK_LEAK_B", value="super-secret-beta", is_secret=True, is_active=True)

        body = api_client.get(CONFIG_PREFIX, user=authed_user).json()

        assert "super-secret-alpha" not in response_text(body)
        assert "super-secret-beta" not in response_text(body)


# =====================================================================
# 场景 5: 架构回归
# =====================================================================


class TestArchitectureRegression:
    """验证 API 层已不再直连 Repository（四层架构修复），且旧 mock 测试保持兼容。"""

    def test_api_module_has_no_repository_reference(self) -> None:
        """apps.core.api 模块不再持有 SystemConfigRepository 引用。"""
        import apps.core.api as api_module

        assert not hasattr(api_module, "_repository")
        assert not any("Repository" in name for name in dir(api_module))

    def test_api_module_source_uses_service_not_repository(self) -> None:
        """源码中走 SystemConfigService，不再出现 SystemConfigRepository。"""
        import inspect

        import apps.core.api as api_module

        source = inspect.getsource(api_module)
        assert "SystemConfigService" in source
        assert "SystemConfigRepository" not in source

    def test_service_uses_repository_for_all_active(self) -> None:
        """get_all_active_configs 走 repository.get_all_active（非 Model.objects 直连）。"""
        from unittest.mock import MagicMock

        from apps.core.services.system_config_service import SystemConfigService

        repo = MagicMock()
        repo.get_all_active.return_value = []
        service = SystemConfigService(repository=repo)

        service.get_all_active_configs()

        repo.get_all_active.assert_called_once()

    def test_service_get_config_by_key_uses_repository(self) -> None:
        """get_config_by_key 走 repository.get_by_key。"""
        from unittest.mock import MagicMock

        from apps.core.services.system_config_service import SystemConfigService

        repo = MagicMock()
        repo.get_by_key.return_value = None
        service = SystemConfigService(repository=repo)

        result = service.get_config_by_key("ANY_KEY")

        repo.get_by_key.assert_called_once_with("ANY_KEY")
        assert result is None

    @pytest.mark.django_db
    def test_aget_value_uses_repository_aget_active_by_key(self) -> None:
        """aget_value 走 repository.aget_active_by_key（本分支新增的 repo 方法）。"""
        from unittest.mock import AsyncMock, MagicMock, patch

        from apps.core.repositories.system_config_repository import SystemConfigRepository
        from apps.core.services.system_config_service import SystemConfigService

        repo = MagicMock(spec=SystemConfigRepository)
        cfg = MagicMock()
        cfg.value = "from-repo"
        cfg.is_secret = False
        repo.aget_active_by_key = AsyncMock(return_value=cfg)

        with patch(
            "apps.core.services.system_config_service.SystemConfigRepository",
            return_value=repo,
        ):
            result = async_to_sync(SystemConfigService.aget_value)("REPO_KEY", "dflt")

        assert result == "from-repo"
        repo.aget_active_by_key.assert_awaited_once_with("REPO_KEY")

    def test_repository_has_aget_active_by_key(self) -> None:
        """SystemConfigRepository 提供 aget_active_by_key 方法。"""
        from apps.core.repositories.system_config_repository import SystemConfigRepository

        assert hasattr(SystemConfigRepository, "aget_active_by_key")

    @pytest.mark.django_db
    def test_repository_aget_active_by_key_filters_inactive(self) -> None:
        """aget_active_by_key 只返回 is_active=True 的记录。"""
        from apps.core.repositories.system_config_repository import SystemConfigRepository

        async def _run() -> tuple[Any, Any]:
            await SystemConfig.objects.acreate(key="E2E_REPO_ACTIVE", value="on", is_active=True)
            await SystemConfig.objects.acreate(key="E2E_REPO_INACTIVE", value="off", is_active=False)
            repo = SystemConfigRepository()
            return (
                await repo.aget_active_by_key("E2E_REPO_ACTIVE"),
                await repo.aget_active_by_key("E2E_REPO_INACTIVE"),
            )

        active, inactive = async_to_sync(_run)()

        assert active is not None
        assert active.value == "on"
        assert inactive is None
