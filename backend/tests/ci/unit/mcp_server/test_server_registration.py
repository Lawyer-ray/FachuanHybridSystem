"""Snapshot / registration tests for MCP Server tools.

These tests verify structural integrity of the MCP tool registry without
actually calling any tool (no Django setup, no HTTP, no DB).

They act as a safety net so that:
- accidental deletions from __all__ are caught immediately
- every tool function has the metadata MCP requires (docstring + type hints)
- server.py imports and registers every function listed in __all__
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers – read source files without importing heavy dependencies
# (importing mcp_server.tools transitively pulls in httpx, Django, etc.)
# ---------------------------------------------------------------------------

_TOOLS_INIT = Path(__file__).resolve().parents[4] / "mcp_server" / "tools" / "__init__.py"
_SERVER_PY = Path(__file__).resolve().parents[4] / "mcp_server" / "server.py"

assert _TOOLS_INIT.exists(), f"tools/__init__.py not found at {_TOOLS_INIT}"
assert _SERVER_PY.exists(), f"server.py not found at {_SERVER_PY}"


def _parse_all_from_init() -> list[str]:
    """Extract all __all__ entries from mcp_server/tools/__init__.py by AST-free
    regex parsing (avoids importing the module which triggers Django/HTTP).

    Handles both ``__all__ = [...]`` and conditional ``__all__ += [...]`` blocks."""
    source = _TOOLS_INIT.read_text()
    names: list[str] = []
    for m in re.finditer(r"__all__\s*[\+]?=\s*\[(.*?)\]", source, re.DOTALL):
        names.extend(re.findall(r'"(\w+)"', m.group(1)))
    assert names, "Could not find __all__ in tools/__init__.py"
    return names


def _parse_registered_from_server() -> set[str]:
    """Extract function names passed to mcp.tool()() in server.py."""
    source = _SERVER_PY.read_text()
    return set(re.findall(r"mcp\.tool\(\)\((\w+)\)", source))


def _parse_imports_from_server() -> set[str]:
    """Extract all function names imported in server.py (both unconditional
    and conditional import blocks)."""
    source = _SERVER_PY.read_text()
    imports: set[str] = set()
    for m in re.finditer(r"from mcp_server\.tools import \((.*?)\)", source, re.DOTALL):
        imports.update(re.findall(r"^\s*(\w+)\s*(?:,|$)", m.group(1), re.MULTILINE))
    assert imports, "Could not find 'from mcp_server.tools import (...)' in server.py"
    return imports


# Eagerly parse once so every test can reuse the results.
_ALL_TOOLS = _parse_all_from_init()
_REGISTERED = _parse_registered_from_server()
_SERVER_IMPORTS = _parse_imports_from_server()

# The real import still requires Django/httpx; we do it once under a fixture.
_real_module = None


def _get_tools_module():
    """Lazily import the real module (triggers Django setup)."""
    global _real_module
    if _real_module is None:
        import mcp_server.tools as _m

        _real_module = _m
    return _real_module


# ---------------------------------------------------------------------------
# Plugin-dependent tool sets
# ---------------------------------------------------------------------------
# These tools are conditionally exported in __all__ (behind ``if _HAS_*``
# guards).  The regex parser picks them up from source regardless, but the
# *real* module only exposes them when the plugin submodule is present.
# We detect availability at import time and filter them out of parameterised
# tests that use ``getattr`` on the live module.

COURT_FILING_TOOLS = frozenset({
    "execute_court_filing",
    "get_court_filing_case_info",
    "get_court_filing_session",
})

GUARANTEE_TOOLS = frozenset({
    "bind_guarantee_quote",
    "delete_guarantee_binding",
    "delete_guarantee_quote",
    "ensure_guarantee_quote",
    "execute_guarantee",
    "get_guarantee_case_info",
    "get_guarantee_session",
    "retry_guarantee_quote",
})

PRESERVATION_QUOTE_TOOLS = frozenset({
    "create_preservation_quote",
    "execute_preservation_quote",
    "get_preservation_quote",
    "list_preservation_quotes",
    "retry_preservation_quote",
})

ALL_PLUGIN_TOOLS = COURT_FILING_TOOLS | GUARANTEE_TOOLS | PRESERVATION_QUOTE_TOOLS


def _plugin_tools_available() -> frozenset[str]:
    """Return the subset of ALL_PLUGIN_TOOLS that are actually importable."""
    available: set[str] = set()
    try:
        from mcp_server.tools import automation
    except (ImportError, Exception):
        # If the automation module itself can't be imported, no plugin tools
        return frozenset()

    mod = _get_tools_module()
    for name in ALL_PLUGIN_TOOLS:
        if hasattr(mod, name):
            available.add(name)
    return frozenset(available)


_AVAILABLE_PLUGIN_TOOLS = _plugin_tools_available()


def _available_tools() -> list[str]:
    """Return the subset of _ALL_TOOLS that are actually present in the
    live module (i.e. excluding plugin tools whose plugin is not installed)."""
    missing_plugins = ALL_PLUGIN_TOOLS - _AVAILABLE_PLUGIN_TOOLS
    return [n for n in _ALL_TOOLS if n not in missing_plugins]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAllListSnapshot:
    """Snapshot test: the __all__ list should not shrink accidentally."""

    def test_all_has_minimum_count(self):
        """Catch accidental mass deletions from __all__."""
        assert len(_ALL_TOOLS) >= 350, (
            f"Expected >= 350 tools in __all__, got {len(_ALL_TOOLS)}. "
            "If you intentionally removed tools, update this threshold."
        )

    def test_all_names_are_unique(self):
        dupes = [n for n in _ALL_TOOLS if _ALL_TOOLS.count(n) > 1]
        assert not dupes, f"Duplicate names in __all__: {set(dupes)}"

    def test_all_names_are_sorted_by_section(self):
        """We don't enforce alphabetical order, but every name must be a
        valid Python identifier."""
        for name in _ALL_TOOLS:
            assert name.isidentifier(), f"Invalid identifier in __all__: {name!r}"


class TestCallableAndMetadata:
    """Verify every tool function is callable and has MCP-required metadata."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        self.tools = _get_tools_module()

    @pytest.mark.parametrize("name", _available_tools(), ids=lambda n: n)
    def test_is_callable(self, name: str):
        fn = getattr(self.tools, name, None)
        assert fn is not None, f"{name} not found in mcp_server.tools"
        assert callable(fn), f"{name} is not callable"

    @pytest.mark.parametrize("name", _available_tools(), ids=lambda n: n)
    def test_has_docstring(self, name: str):
        fn = getattr(self.tools, name)
        doc = getattr(fn, "__doc__", None)
        assert doc and doc.strip(), (
            f"{name} is missing a docstring. "
            "MCP uses the docstring as the tool description."
        )

    @pytest.mark.parametrize("name", _available_tools(), ids=lambda n: n)
    def test_has_type_annotations(self, name: str):
        """Every parameter (except 'request' injected by some frameworks)
        should have a type annotation."""
        fn = getattr(self.tools, name)
        sig = inspect.signature(fn)
        for param_name, param in sig.parameters.items():
            if param_name in ("request", "ctx"):
                # Framework-injected params may lack annotations
                continue
            assert param.annotation is not inspect.Parameter.empty, (
                f"{name}({param_name}) is missing a type annotation. "
                "MCP requires type hints to generate the JSON schema."
            )


class TestServerRegistration:
    """Verify server.py imports and registers every function in __all__."""

    # Functions exported in __all__ but not imported/registered in server.py.
    # These are exposed for programmatic use (e.g. other modules import them
    # directly from mcp_server.tools) but are not top-level MCP tools.
    KNOWN_UNREGISTERED = {
        "create_workflow_template",
        "delete_workflow_run",
        "delete_workflow_template",
        "duplicate_workflow_template",
        "get_step_registry",
        "get_step_registry_flat",
        "get_workflow_template",
        "list_workflow_templates",
        "start_workflow_from_steps",
        "update_workflow_template",
    }

    def test_all_functions_imported_in_server(self):
        """Every name in __all__ should appear in server.py's import block."""
        expected_imported = set(_ALL_TOOLS) - self.KNOWN_UNREGISTERED
        missing = expected_imported - _SERVER_IMPORTS
        assert not missing, (
            f"These __all__ names are NOT imported in server.py: {sorted(missing)}"
        )

    def test_all_functions_registered_via_mcp_tool(self):
        """Every name in __all__ should have a corresponding mcp.tool()() call
        in server.py (excluding known unregistered functions)."""
        expected_registered = set(_ALL_TOOLS) - self.KNOWN_UNREGISTERED
        not_registered = expected_registered - _REGISTERED
        assert not not_registered, (
            f"These __all__ names are NOT registered in server.py: "
            f"{sorted(not_registered)}"
        )

    def test_no_orphan_registrations(self):
        """Every mcp.tool()() call in server.py should reference an imported
        function (guards against typos)."""
        orphan = _REGISTERED - set(_ALL_TOOLS)
        assert not orphan, (
            f"These functions are registered in server.py but NOT in __all__: "
            f"{sorted(orphan)}"
        )

    def test_registration_count_matches(self):
        """The number of mcp.tool()() calls should match the number of
        __all__ entries minus known unregistered exceptions."""
        expected = len(_ALL_TOOLS) - len(self.KNOWN_UNREGISTERED)
        assert len(_REGISTERED) == expected, (
            f"Expected {expected} registrations in server.py, got {len(_REGISTERED)}. "
            "Either a tool was added/removed from __all__ or server.py is out of sync."
        )
