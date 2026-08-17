"""Tests for apps.core.apps: macOS 上 django-q mp context spawn patch."""

from __future__ import annotations

import multiprocessing
import sys

import pytest
from django_q import cluster as django_q_cluster

from apps.core.apps import CoreConfig


def _get_start_method() -> str:
    """读取当前 get_mp_context 返回的 context 的 start method。"""
    return str(django_q_cluster.get_mp_context().get_start_method())


class TestDjangoQSpawnPatch:
    def test_darwin_patches_to_spawn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(
            django_q_cluster,
            "get_mp_context",
            lambda: multiprocessing.get_context("fork"),
        )

        CoreConfig._patch_django_q_mp_context_for_macos()

        assert _get_start_method() == "spawn"

    def test_patch_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(
            django_q_cluster,
            "get_mp_context",
            lambda: multiprocessing.get_context("fork"),
        )

        CoreConfig._patch_django_q_mp_context_for_macos()
        patched_once = django_q_cluster.get_mp_context
        assert patched_once is not None
        CoreConfig._patch_django_q_mp_context_for_macos()

        assert django_q_cluster.get_mp_context is patched_once
        assert _get_start_method() == "spawn"

    def test_non_darwin_platform_not_patched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        original = django_q_cluster.get_mp_context

        CoreConfig._patch_django_q_mp_context_for_macos()

        assert django_q_cluster.get_mp_context is original

    def test_already_patched_function_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")

        def _pre_patched() -> str:
            return "spawn"

        _pre_patched._fachuan_spawn_patched = True  # type: ignore[attr-defined]
        monkeypatch.setattr(django_q_cluster, "get_mp_context", _pre_patched)

        CoreConfig._patch_django_q_mp_context_for_macos()

        assert django_q_cluster.get_mp_context is _pre_patched
