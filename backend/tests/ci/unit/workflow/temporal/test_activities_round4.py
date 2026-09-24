"""Tests for workflow/temporal/activities.py — Round 4 deeper coverage.

Covers: collect_case_facts, list_case_materials, analyze_single_evidence,
summarize_evidence, apply_arrangement, build_litigation_context,
generate_complaint, generate_complaint_simple, generic_delay,
generic_http_request with non-JSON response, generic_code_exec with safe builtins,
fetch_template_schema.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper to unwrap Temporal activity decorators
# ---------------------------------------------------------------------------


def _fn(activity_fn):
    return activity_fn.fn if hasattr(activity_fn, "fn") else activity_fn


# ---------------------------------------------------------------------------
# collect_case_facts
# ---------------------------------------------------------------------------


class TestCollectCaseFacts:
    @pytest.mark.asyncio
    async def test_returns_case_data(self):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test Case"
        mock_case.cause_of_action = "买卖合同纠纷"
        mock_case.target_amount = 100000
        mock_case.case_type = "civil"
        mock_case.start_date = None
        mock_case.contract = None

        mock_party = MagicMock()
        mock_party.client = MagicMock()
        mock_party.client.name = "张三"
        mock_party.legal_status = "plaintiff"
        mock_party.client.id_number = "110101199001011234"
        mock_party.client.address = "北京市"

        mock_case_model = MagicMock()
        mock_case_model.objects.select_related.return_value.aget = AsyncMock(return_value=mock_case)

        mock_party_model = MagicMock()

        async def mock_filter(**kw):
            yield mock_party

        mock_party_model.objects.filter.return_value.select_related = lambda *a: mock_filter()

        with patch.dict(
            "sys.modules",
            {
                "apps.cases.models": MagicMock(Case=mock_case_model),
                "apps.cases.models.party": MagicMock(CaseParty=mock_party_model),
            },
        ):
            from apps.workflow.temporal.activities import collect_case_facts

            result = await _fn(collect_case_facts)(case_id=1)
            assert result["case_name"] == "Test Case"
            assert result["cause_of_action"] == "买卖合同纠纷"
            assert result["target_amount"] == "100000"
            assert len(result["parties"]) == 1
            assert result["parties"][0]["name"] == "张三"

    @pytest.mark.asyncio
    async def test_case_with_none_target_amount(self):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test"
        mock_case.cause_of_action = "纠纷"
        mock_case.target_amount = None
        mock_case.case_type = "civil"
        mock_case.start_date = None

        mock_case_model = MagicMock()
        mock_case_model.objects.select_related.return_value.aget = AsyncMock(return_value=mock_case)

        mock_party_model = MagicMock()

        async def mock_filter(**kw):
            return
            yield  # make it an async generator

        mock_party_model.objects.filter.return_value.select_related = lambda *a: mock_filter()

        with patch.dict(
            "sys.modules",
            {
                "apps.cases.models": MagicMock(Case=mock_case_model),
                "apps.cases.models.party": MagicMock(CaseParty=mock_party_model),
            },
        ):
            from apps.workflow.temporal.activities import collect_case_facts

            result = await _fn(collect_case_facts)(case_id=1)
            assert result["target_amount"] is None
            assert result["parties"] == []


# ---------------------------------------------------------------------------
# list_case_materials
# ---------------------------------------------------------------------------


class TestListCaseMaterials:
    @pytest.mark.asyncio
    async def test_returns_materials(self):
        mock_mat = MagicMock()
        mock_mat.id = 1
        mock_mat.type_name = "合同"
        mock_mat.file_path = "/path/to/file.pdf"
        mock_mat.content_type = "application/pdf"

        mock_model = MagicMock()

        async def mock_filter(**kw):
            yield mock_mat

        mock_model.objects.filter.return_value.order_by = lambda *a: mock_filter()

        with patch.dict(
            "sys.modules",
            {
                "apps.cases.models": MagicMock(CaseMaterial=mock_model),
            },
        ):
            from apps.workflow.temporal.activities import list_case_materials

            result = await _fn(list_case_materials)(case_id=1)
            assert len(result) == 1
            assert result[0]["name"] == "合同"


# ---------------------------------------------------------------------------
# analyze_single_evidence
# ---------------------------------------------------------------------------


class TestAnalyzeSingleEvidence:
    @pytest.mark.asyncio
    async def test_with_extracted_text(self):
        with (
            patch("apps.workflow.temporal.activities._llm_chat", new_callable=AsyncMock) as mock_llm,
            patch("apps.core.services.pdf_utils.extract_text", return_value="证据文本内容") as mock_extract,
        ):
            mock_llm.return_value = "分析结果"
            from apps.workflow.temporal.activities import analyze_single_evidence

            result = await _fn(analyze_single_evidence)({"id": 1, "name": "合同", "file_path": "/path/file.pdf"})
            assert result["material_id"] == 1
            assert result["material_name"] == "合同"
            assert result["analysis"] == "分析结果"
            mock_extract.assert_called_once_with("/path/file.pdf")

    @pytest.mark.asyncio
    async def test_with_empty_text_fallback(self):
        with (
            patch("apps.workflow.temporal.activities._llm_chat", new_callable=AsyncMock) as mock_llm,
            patch("apps.core.services.pdf_utils.extract_text", return_value=""),
        ):
            mock_llm.return_value = "fallback analysis"
            from apps.workflow.temporal.activities import analyze_single_evidence

            result = await _fn(analyze_single_evidence)({"id": 2, "name": "收据", "file_path": "/path/file.pdf"})
            assert result["analysis"] == "fallback analysis"


# ---------------------------------------------------------------------------
# summarize_evidence
# ---------------------------------------------------------------------------


class TestSummarizeEvidence:
    @pytest.mark.asyncio
    async def test_summarizes_analyses(self):
        with patch("apps.workflow.temporal.activities._llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "汇总结果"
            from apps.workflow.temporal.activities import summarize_evidence

            analyses = [
                {"material_name": "合同", "analysis": "合同分析"},
                {"material_name": "收据", "analysis": "收据分析"},
            ]
            result = await _fn(summarize_evidence)(analyses)
            assert result["summary"] == "汇总结果"
            assert result["evidence_count"] == 2


# ---------------------------------------------------------------------------
# apply_arrangement
# ---------------------------------------------------------------------------


class TestApplyArrangement:
    """apply_arrangement 把材料排列写入 CaseMaterialGroupOrder（经 save_group_order）。"""

    @staticmethod
    def _queryset(materials: list[Any]) -> MagicMock:
        """构造支持 `async for` 的假 queryset，且可链 .only()。"""

        async def _aiter(*_args: Any, **_kwargs: Any):
            for m in materials:
                yield m

        qs = MagicMock()
        qs.only.return_value = _aiter()
        return qs

    @pytest.mark.asyncio
    async def test_writes_group_order_via_service(self):
        """两个不同分组的材料应各自触发一次 save_group_order。"""
        m1 = SimpleNamespace(id=1, category="party", side="our", supervising_authority_id=None, type_id=10)
        m2 = SimpleNamespace(id=2, category="party", side="our", supervising_authority_id=None, type_id=20)
        m3 = SimpleNamespace(id=3, category="non_party", side=None, supervising_authority_id=5, type_id=30)

        with (
            patch("apps.cases.models.CaseMaterial.objects.filter", return_value=self._queryset([m1, m2, m3])),
            patch("apps.cases.services.material.wiring.build_case_material_service") as mock_build,
        ):
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            from apps.workflow.temporal.activities import apply_arrangement

            arrangement = [
                {"id": 1, "name": "A", "reason": "first"},
                {"id": 2, "name": "B", "reason": "second"},
                {"id": 3, "name": "C", "reason": "third"},
            ]
            await _fn(apply_arrangement)(case_id=1, arrangement=arrangement)

            assert mock_service.save_group_order.call_count == 2
            calls = {
                c.kwargs["category"]: c.kwargs["ordered_type_ids"] for c in mock_service.save_group_order.call_args_list
            }
            assert calls["party"] == [10, 20]
            assert calls["non_party"] == [30]

    @pytest.mark.asyncio
    async def test_skips_items_without_id(self):
        """全部条目都无有效 id 时不应查库、更不应写排序。"""
        with (
            patch("apps.cases.models.CaseMaterial.objects.filter") as mock_filter,
            patch("apps.cases.services.material.wiring.build_case_material_service") as mock_build,
        ):
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            from apps.workflow.temporal.activities import apply_arrangement

            arrangement = [{"id": 0, "name": "A"}, {"name": "B"}]
            await _fn(apply_arrangement)(case_id=1, arrangement=arrangement)

            mock_filter.assert_not_called()
            mock_service.save_group_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplicates_material_ids(self):
        """同一 type 在排列中重复出现只记一次，保持首次出现的顺序。"""
        m1 = SimpleNamespace(id=1, category="party", side="our", supervising_authority_id=None, type_id=10)

        with (
            patch("apps.cases.models.CaseMaterial.objects.filter", return_value=self._queryset([m1])),
            patch("apps.cases.services.material.wiring.build_case_material_service") as mock_build,
        ):
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            from apps.workflow.temporal.activities import apply_arrangement

            arrangement = [{"id": 1}, {"id": 1}, {"id": 1}]
            await _fn(apply_arrangement)(case_id=1, arrangement=arrangement)

            assert mock_service.save_group_order.call_count == 1
            assert mock_service.save_group_order.call_args.kwargs["ordered_type_ids"] == [10]


# ---------------------------------------------------------------------------
# build_litigation_context
# ---------------------------------------------------------------------------


class TestBuildLitigationContext:
    @pytest.mark.asyncio
    async def test_builds_context(self):
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.name = "Test"
        mock_case.cause_of_action = "纠纷"
        mock_case.target_amount = 50000
        mock_case.case_type = "civil"

        mock_case_model = MagicMock()
        mock_case_model.objects.select_related.return_value.aget = AsyncMock(return_value=mock_case)

        mock_party_model = MagicMock()

        async def mock_filter(**kw):
            return
            yield

        mock_party_model.objects.filter.return_value.select_related = lambda *a: mock_filter()

        with patch.dict(
            "sys.modules",
            {
                "apps.cases.models": MagicMock(Case=mock_case_model),
                "apps.cases.models.party": MagicMock(CaseParty=mock_party_model),
            },
        ):
            from apps.workflow.temporal.activities import build_litigation_context

            result = await _fn(build_litigation_context)(
                case_id=1,
                summary={"summary": "test"},
                arrangement=[],
            )
            assert result["case"]["id"] == 1
            assert result["evidence_summary"] == {"summary": "test"}
            assert result["arrangement"] == []


# ---------------------------------------------------------------------------
# generate_complaint
# ---------------------------------------------------------------------------


class TestGenerateComplaint:
    @pytest.mark.asyncio
    async def test_calls_litigation_service(self):
        mock_service = MagicMock()
        mock_service.generate_complaint = MagicMock(return_value={"content": "起诉状"})

        mock_builder = MagicMock()
        mock_builder.extract_complaint_prompt_data = MagicMock(return_value={"facts": "test"})

        mock_case_service = MagicMock()
        mock_case_service.get_case_by_id_internal.return_value = MagicMock()

        mock_service_locator = MagicMock()
        mock_service_locator.get_case_service.return_value = mock_case_service

        with patch.dict(
            "sys.modules",
            {
                "apps.documents.services.generation.litigation_generation_service": MagicMock(
                    LitigationGenerationService=MagicMock(return_value=mock_service)
                ),
                "apps.documents.services.generation.litigation_context_builder": MagicMock(
                    LitigationContextBuilder=MagicMock(return_value=mock_builder)
                ),
                "apps.core.interfaces": MagicMock(ServiceLocator=mock_service_locator),
            },
        ):
            from apps.workflow.temporal.activities import generate_complaint

            result = await _fn(generate_complaint)(
                case_id=1,
                feedback="修改意见",
            )
            assert result == {"result": {"content": "起诉状"}}


# ---------------------------------------------------------------------------
# generate_complaint_simple
# ---------------------------------------------------------------------------


class TestGenerateComplaintSimple:
    @pytest.mark.asyncio
    async def test_generates_simple(self):
        with patch("apps.workflow.temporal.activities._llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "起诉状内容"
            from apps.workflow.temporal.activities import generate_complaint_simple

            result = await _fn(generate_complaint_simple)(case_id=1, facts={"key": "value"})
            assert result["content"] == "起诉状内容"
            assert result["case_id"] == 1


# ---------------------------------------------------------------------------
# generic_delay — async sleep
# ---------------------------------------------------------------------------


class TestGenericDelayAsync:
    @pytest.mark.asyncio
    async def test_calls_asyncio_sleep(self):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            from apps.workflow.temporal.activities import generic_delay

            await _fn(generic_delay)(0.5)
            mock_sleep.assert_called_once_with(30.0)  # 0.5 * 60


# ---------------------------------------------------------------------------
# generic_http_request — non-JSON response
# ---------------------------------------------------------------------------


class TestGenericHttpRequestNonJson:
    @pytest.mark.asyncio
    async def test_non_json_text_response(self):
        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value="<html>OK</html>")
        mock_resp.status = 200

        class _FakeCM:
            def __init__(self, val):
                self._val = val

            async def __aenter__(self):
                return self._val

            async def __aexit__(self, *a):
                pass

        class _FakeSession:
            def request(self, method, **kw):
                return _FakeCM(mock_resp)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession.return_value = _FakeSession()

        with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
            from apps.workflow.temporal.activities import generic_http_request

            result = await _fn(generic_http_request)("GET", "https://example.com")
            assert result["status_code"] == 200
            assert result["data"] == "<html>OK</html>"


# ---------------------------------------------------------------------------
# generic_code_exec — more builtins
# ---------------------------------------------------------------------------


class TestGenericCodeExecBuiltins:
    @pytest.mark.asyncio
    async def test_code_with_safe_builtins(self):
        from apps.workflow.temporal.activities import generic_code_exec

        result = await _fn(generic_code_exec)("result = len([1,2,3]) + max(10, 20)", {"case_id": 1})
        assert result["result"] == 23

    @pytest.mark.asyncio
    async def test_code_with_json_builtin(self):
        from apps.workflow.temporal.activities import generic_code_exec

        result = await _fn(generic_code_exec)("data = json.dumps({'a': 1})", {"case_id": 1})
        assert "data" in result

    @pytest.mark.asyncio
    async def test_code_produces_multiple_vars(self):
        from apps.workflow.temporal.activities import generic_code_exec

        result = await _fn(generic_code_exec)("x = 1\ny = 2\nz = x + y", {})
        assert result["x"] == 1
        assert result["y"] == 2
        assert result["z"] == 3


# ---------------------------------------------------------------------------
# fetch_template_schema
# ---------------------------------------------------------------------------


class TestFetchTemplateSchema:
    @pytest.mark.asyncio
    async def test_returns_schema(self):
        mock_tpl = MagicMock()
        mock_tpl.id = 1
        mock_tpl.name = "Test Template"
        mock_tpl.slug = "test-template"
        mock_tpl.steps_schema = [{"id": "step1"}]

        mock_model = MagicMock()
        mock_model.objects.aget = AsyncMock(return_value=mock_tpl)

        with patch.dict(
            "sys.modules",
            {
                "apps.workflow.models": MagicMock(WorkflowTemplate=mock_model),
            },
        ):
            from apps.workflow.temporal.activities import fetch_template_schema

            result = await _fn(fetch_template_schema)(template_id=1)
            assert result["template_id"] == 1
            assert result["name"] == "Test Template"
            assert result["steps_schema"] == [{"id": "step1"}]
