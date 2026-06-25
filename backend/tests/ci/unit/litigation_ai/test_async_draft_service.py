"""Tests for async draft service (P0: asyncio.run() removal)."""

from __future__ import annotations

import asyncio
import inspect

import pytest


@pytest.mark.asyncio
class TestDraftServiceAsync:
    async def test_generate_draft_for_agent_is_async(self):
        """generate_draft_for_agent should be an async function (not using asyncio.run)."""
        from apps.litigation_ai.services.generation.draft_service import DraftService

        svc = DraftService()
        assert inspect.iscoroutinefunction(svc.generate_draft_for_agent), (
            "generate_draft_for_agent should be async def"
        )

    async def test_no_asyncio_run_in_source(self):
        """generate_draft_for_agent source should not contain asyncio.run()."""
        import inspect
        from apps.litigation_ai.services.generation.draft_service import DraftService

        source = inspect.getsource(DraftService.generate_draft_for_agent)
        assert "asyncio.run(" not in source, (
            "generate_draft_for_agent should not use asyncio.run() — use await directly"
        )

    async def test_tools_generate_draft_is_async(self):
        """The generate_draft tool should be callable as async via ainvoke."""
        from apps.litigation_ai.agent.tools import generate_draft

        # The tool should have an ainvoke method (from _SimpleTool)
        assert hasattr(generate_draft, 'ainvoke'), (
            "generate_draft tool should have ainvoke method"
        )
