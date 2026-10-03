"""allow_async_unsafe 上下文管理器的环境变量恢复行为。

重点验证：放行只发生在 with 块内，退出（含异常退出、嵌套退出）后
DJANGO_ALLOW_ASYNC_UNSAFE 恢复原值（未预置时彻底移除），不再永久污染进程。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from apps.core.infrastructure.async_context import allow_async_unsafe

_ENV_KEY = "DJANGO_ALLOW_ASYNC_UNSAFE"


@pytest.fixture(autouse=True)
def _restore_env() -> Iterator[None]:
    """无论用例结果如何，退出时还原 DJANGO_ALLOW_ASYNC_UNSAFE 原值，避免污染其他用例。"""
    old = os.environ.get(_ENV_KEY)
    os.environ.pop(_ENV_KEY, None)
    yield
    if old is None:
        os.environ.pop(_ENV_KEY, None)
    else:
        os.environ[_ENV_KEY] = old


def test_nested_restore_when_absent() -> None:
    """未预置时：嵌套退出内层仍放行，外层退出后彻底移除。"""
    assert _ENV_KEY not in os.environ
    with allow_async_unsafe():
        assert os.environ.get(_ENV_KEY) == "true"
        with allow_async_unsafe():
            assert os.environ.get(_ENV_KEY) == "true"
        # 内层退出后仍处于外层放行中
        assert os.environ.get(_ENV_KEY) == "true"
    # 外层退出后彻底移除，而不是残留 "true"
    assert _ENV_KEY not in os.environ


def test_preset_value_restored() -> None:
    """预置 "false" 时：with 内放行，退出后恢复 "false"。"""
    os.environ[_ENV_KEY] = "false"
    with allow_async_unsafe():
        assert os.environ.get(_ENV_KEY) == "true"
        with allow_async_unsafe():
            assert os.environ.get(_ENV_KEY) == "true"
        assert os.environ.get(_ENV_KEY) == "true"
    assert os.environ.get(_ENV_KEY) == "false"


def test_exception_still_restores_absent() -> None:
    """with 内抛异常：退出后仍恢复（未预置时移除）。"""
    assert _ENV_KEY not in os.environ
    with pytest.raises(RuntimeError), allow_async_unsafe():
        assert os.environ.get(_ENV_KEY) == "true"
        raise RuntimeError("boom")
    assert _ENV_KEY not in os.environ


def test_exception_restores_preset_value() -> None:
    """with 内抛异常：退出后恢复预置值。"""
    os.environ[_ENV_KEY] = "keep"
    with pytest.raises(ValueError), allow_async_unsafe():
        assert os.environ.get(_ENV_KEY) == "true"
        raise ValueError("boom")
    assert os.environ.get(_ENV_KEY) == "keep"
