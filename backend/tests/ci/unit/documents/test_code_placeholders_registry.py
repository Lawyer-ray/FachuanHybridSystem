"""Tests for documents/services/code_placeholders/registry.py.

Covers: CodePlaceholderRegistry singleton, register, upsert, list_definitions, clear,
expose_placeholders decorator.
"""
from __future__ import annotations

from typing import Any

from apps.documents.services.code_placeholders.registry import (
    CodePlaceholderDefinition,
    CodePlaceholderRegistry,
    expose_placeholders,
)


class TestCodePlaceholderDefinition:
    def test_frozen_dataclass(self):
        d = CodePlaceholderDefinition(
            key="test.key",
            source="test",
            category="test",
            display_name="Test",
            description="A test",
            example_value="val",
        )
        assert d.key == "test.key"
        assert d.source == "test"

    def test_defaults(self):
        d = CodePlaceholderDefinition(
            key="k", source="s", category="c"
        )
        assert d.display_name == ""
        assert d.description == ""
        assert d.example_value == ""


class TestCodePlaceholderRegistrySingleton:
    def test_singleton(self):
        a = CodePlaceholderRegistry()
        b = CodePlaceholderRegistry()
        assert a is b

    def test_clear(self):
        reg = CodePlaceholderRegistry()
        reg.clear()
        assert reg.list_definitions() == []


class TestCodePlaceholderRegistryRegister:
    def test_register_adds_definitions(self):
        reg = CodePlaceholderRegistry()
        reg.clear()
        defs = [
            CodePlaceholderDefinition(key="a", source="s1", category="c1"),
            CodePlaceholderDefinition(key="b", source="s2", category="c2"),
        ]
        reg.register(defs)
        result = reg.list_definitions()
        assert len(result) == 2

    def test_register_does_not_overwrite(self):
        reg = CodePlaceholderRegistry()
        reg.clear()
        d1 = CodePlaceholderDefinition(key="a", source="s1", category="c1", display_name="First")
        d2 = CodePlaceholderDefinition(key="a", source="s2", category="c2", display_name="Second")
        reg.register([d1])
        reg.register([d2])
        result = reg.list_definitions()
        assert len(result) == 1
        assert result[0].display_name == "First"


class TestCodePlaceholderRegistryUpsert:
    def test_upsert_adds(self):
        reg = CodePlaceholderRegistry()
        reg.clear()
        d = CodePlaceholderDefinition(key="x", source="s", category="c", display_name="X")
        reg.upsert([d])
        assert len(reg.list_definitions()) == 1

    def test_upsert_overwrites(self):
        reg = CodePlaceholderRegistry()
        reg.clear()
        d1 = CodePlaceholderDefinition(key="x", source="s1", category="c1", display_name="Old")
        d2 = CodePlaceholderDefinition(key="x", source="s2", category="c2", display_name="New")
        reg.register([d1])
        reg.upsert([d2])
        result = reg.list_definitions()
        assert len(result) == 1
        assert result[0].display_name == "New"


class TestCodePlaceholderRegistryListDefinitions:
    def test_sorted_by_key(self):
        reg = CodePlaceholderRegistry()
        reg.clear()
        reg.register([
            CodePlaceholderDefinition(key="z", source="s", category="c"),
            CodePlaceholderDefinition(key="a", source="s", category="c"),
            CodePlaceholderDefinition(key="m", source="s", category="c"),
        ])
        result = reg.list_definitions()
        keys = [d.key for d in result]
        assert keys == ["a", "m", "z"]


class TestExposePlaceholdersDecorator:
    def test_attaches_definitions(self):
        reg = CodePlaceholderRegistry()
        reg.clear()

        @expose_placeholders(
            keys=["key1", "key2"],
            source="test_source",
            category="test_cat",
            metadata={
                "key1": {"display_name": "Key One", "description": "desc1", "example_value": "ex1"},
            },
        )
        def my_function():
            pass

        defs = getattr(my_function, "__code_placeholder_definitions__")
        assert len(defs) == 2
        assert defs[0].key == "key1"
        assert defs[0].display_name == "Key One"
        assert defs[0].example_value == "ex1"
        assert defs[1].key == "key2"
        assert defs[1].display_name == ""

    def test_registers_in_registry(self):
        reg = CodePlaceholderRegistry()
        reg.clear()

        @expose_placeholders(
            keys=["reg_key"],
            source="src",
            category="cat",
            description="default desc",
        )
        def my_func():
            pass

        found = [d for d in reg.list_definitions() if d.key == "reg_key"]
        assert len(found) == 1
        assert found[0].description == "default desc"

    def test_no_metadata(self):
        reg = CodePlaceholderRegistry()
        reg.clear()

        @expose_placeholders(
            keys=["simple"],
            source="s",
            category="c",
        )
        def func():
            pass

        defs = getattr(func, "__code_placeholder_definitions__")
        assert defs[0].key == "simple"
        assert defs[0].description == ""

    def test_preserves_original_function(self):
        @expose_placeholders(
            keys=["k"],
            source="s",
            category="c",
        )
        def original():
            return 42

        assert original() == 42
