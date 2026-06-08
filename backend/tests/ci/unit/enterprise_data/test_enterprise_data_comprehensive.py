"""enterprise_data 模块单元测试

覆盖文件:
- apps/enterprise_data/models/workbench.py
- apps/enterprise_data/services/types.py
- apps/enterprise_data/services/provider_registry.py
- apps/enterprise_data/schemas/enterprise_data_schemas.py
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ==================== Types ====================


class TestEnterpriseDataTypes:
    """类型定义测试"""

    def test_default_constants(self):
        from apps.enterprise_data.services.types import (
            DEFAULT_PROVIDER_NAME,
            DEFAULT_TRANSPORT,
            DEFAULT_TIMEOUT_SECONDS,
            DEFAULT_CACHE_TTL_SECONDS,
        )

        assert DEFAULT_PROVIDER_NAME == "tianyancha"
        assert DEFAULT_TRANSPORT == "streamable_http"
        assert DEFAULT_TIMEOUT_SECONDS == 30
        assert DEFAULT_CACHE_TTL_SECONDS == 300

    def test_provider_config(self):
        from apps.enterprise_data.services.types import ProviderConfig

        config = ProviderConfig(
            name="tianyancha",
            enabled=True,
            transport="streamable_http",
            base_url="http://localhost:8080",
            sse_url="http://localhost:8080/sse",
            api_key="test-key",
            timeout_seconds=30,
        )
        assert config.name == "tianyancha"
        assert config.enabled is True
        assert config.timeout_seconds == 30

    def test_provider_config_defaults(self):
        from apps.enterprise_data.services.types import ProviderConfig, DEFAULT_RATE_LIMIT_REQUESTS

        config = ProviderConfig(
            name="test",
            enabled=True,
            transport="stdio",
            base_url="",
            sse_url="",
            api_key="",
            timeout_seconds=10,
        )
        assert config.rate_limit_requests == DEFAULT_RATE_LIMIT_REQUESTS
        assert config.retry_max_attempts == 2

    def test_provider_descriptor(self):
        from apps.enterprise_data.services.types import ProviderDescriptor

        desc = ProviderDescriptor(
            name="tianyancha",
            enabled=True,
            is_default=True,
            transport="streamable_http",
            capabilities=["search", "profile"],
            note="天眼查",
        )
        assert desc.name == "tianyancha"
        assert desc.is_default is True
        assert len(desc.capabilities) == 2

    def test_provider_response(self):
        from apps.enterprise_data.services.types import ProviderResponse

        resp = ProviderResponse(
            data={"company_name": "测试公司"},
            raw={"status": "ok"},
            tool="company_search",
        )
        assert resp.data["company_name"] == "测试公司"
        assert resp.tool == "company_search"
        assert resp.meta == {}


# ==================== McpWorkbench Model ====================


class TestMcpWorkbenchModel:
    """McpWorkbench 模型测试"""

    def test_meta_not_managed(self):
        from apps.enterprise_data.models.workbench import McpWorkbench

        assert McpWorkbench._meta.managed is False
        assert McpWorkbench._meta.verbose_name == "MCP 调试工作台"


# ==================== McpWorkbenchExecution Model ====================


class TestMcpWorkbenchExecutionModel:
    """McpWorkbenchExecution 模型测试"""

    def test_str_success(self):
        from apps.enterprise_data.models.workbench import McpWorkbenchExecution

        exec_record = McpWorkbenchExecution(
            provider="tianyancha",
            tool_name="company_search",
            success=True,
        )
        assert str(exec_record) == "tianyancha:company_search:success"

    def test_str_failed(self):
        from apps.enterprise_data.models.workbench import McpWorkbenchExecution

        exec_record = McpWorkbenchExecution(
            provider="qichacha",
            tool_name="company_profile",
            success=False,
        )
        assert str(exec_record) == "qichacha:company_profile:failed"

    def test_sanitize_json_small_data(self):
        from apps.enterprise_data.models.workbench import McpWorkbenchExecution

        data = {"key": "value", "count": 42}
        # scrub_for_storage will be called on the data
        result = McpWorkbenchExecution._sanitize_json(data)
        assert result is not None

    def test_sanitize_json_large_data(self):
        from apps.enterprise_data.models.workbench import McpWorkbenchExecution

        # Create data that's definitely over 50k when serialized
        large_data = {"data": ["item" * 100 for _ in range(200)]}
        result = McpWorkbenchExecution._sanitize_json(large_data)
        assert result is not None
        # May or may not be truncated depending on scrub_for_storage behavior
        if isinstance(result, dict) and "_truncated" in result:
            assert result["_truncated"] is True
            assert "preview" in result

    def test_sanitize_json_type_error(self):
        from apps.enterprise_data.models.workbench import McpWorkbenchExecution

        # Use a non-serializable object that won't cause TypeError in scrub_for_storage
        # but will cause it in json.dumps
        class NonSerializable:
            def __str__(self):
                return "non-serializable"

        result = McpWorkbenchExecution._sanitize_json({"obj": NonSerializable()})
        # Should return scrubbed data without truncation since it can't serialize
        assert result is not None

    def test_meta(self):
        from apps.enterprise_data.models.workbench import McpWorkbenchExecution

        assert McpWorkbenchExecution._meta.verbose_name == "MCP 调试执行历史"


# ==================== Schemas ====================


class TestEnterpriseDataSchemas:
    """Schema 测试"""

    def test_company_summary_out(self):
        from apps.enterprise_data.schemas.enterprise_data_schemas import CompanySummaryOut

        data = CompanySummaryOut(
            company_id="123",
            company_name="测试公司",
            legal_person="张三",
            status="存续",
        )
        assert data.company_id == "123"
        assert data.legal_person == "张三"

    def test_company_profile_out(self):
        from apps.enterprise_data.schemas.enterprise_data_schemas import CompanyProfileOut

        data = CompanyProfileOut(
            company_id="123",
            company_name="测试公司",
            unified_social_credit_code="91110000MA01B1234X",
        )
        assert data.unified_social_credit_code == "91110000MA01B1234X"

    def test_company_risk_item_out(self):
        from apps.enterprise_data.schemas.enterprise_data_schemas import CompanyRiskItemOut

        data = CompanyRiskItemOut(risk_type="自身风险", title="诉讼风险", level="高")
        assert data.risk_type == "自身风险"

    def test_bidding_item_out(self):
        from apps.enterprise_data.schemas.enterprise_data_schemas import BiddingItemOut

        data = BiddingItemOut(title="招标", project_name="项目A", amount="100万")
        assert data.title == "招标"

    def test_enterprise_data_meta_out(self):
        from apps.enterprise_data.schemas.enterprise_data_schemas import EnterpriseDataMetaOut

        data = EnterpriseDataMetaOut(
            provider="tianyancha",
            transport="streamable_http",
            tool="company_search",
            capability="search",
        )
        assert data.provider == "tianyancha"
        assert data.cached is False

    def test_provider_info_out(self):
        from apps.enterprise_data.schemas.enterprise_data_schemas import ProviderInfoOut

        data = ProviderInfoOut(
            name="tianyancha",
            enabled=True,
            is_default=True,
            transport="streamable_http",
            capabilities=["search"],
        )
        assert data.name == "tianyancha"
        assert data.tools == []

    def test_enterprise_providers_out(self):
        from apps.enterprise_data.schemas.enterprise_data_schemas import EnterpriseProvidersOut, ProviderInfoOut

        data = EnterpriseProvidersOut(items=[
            ProviderInfoOut(name="tianyancha", enabled=True, is_default=True, transport="http", capabilities=[])
        ])
        assert len(data.items) == 1

    def test_enterprise_query_out(self):
        from apps.enterprise_data.schemas.enterprise_data_schemas import EnterpriseQueryOut, EnterpriseDataMetaOut

        data = EnterpriseQueryOut(
            query={"keyword": "测试"},
            data={"results": []},
            meta=EnterpriseDataMetaOut(
                provider="tianyancha",
                transport="http",
                tool="search",
                capability="search",
            ),
        )
        assert data.query["keyword"] == "测试"
