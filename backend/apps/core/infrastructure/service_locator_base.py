"""Module for service locator base."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, ClassVar, TypeVar, cast

T = TypeVar("T")


class BaseServiceLocator:
    _services: ClassVar[dict[str, Any]] = {}
    _scope: ContextVar[dict[str, Any] | None] = ContextVar("service_locator_scope", default=None)

    @classmethod
    def _storage(cls) -> dict[str, Any]:
        scoped = cls._scope.get()
        if scoped is not None:
            return scoped
        return cls._services

    @classmethod
    @contextmanager
    def scope(cls) -> Iterator[type[BaseServiceLocator]]:
        token = cls._scope.set({})
        try:
            yield cls
        finally:
            cls._scope.reset(token)

    @classmethod
    def register(cls, name: str, service: Any) -> None:
        cls._storage()[name] = service

    @classmethod
    def get(cls, name: str) -> Any | None:
        return cls._storage().get(name)

    @classmethod
    def get_or_create(cls, name: str, factory: Callable[[], T]) -> T:
        existing = cls.get(name)
        if existing is not None:
            return cast(T, existing)
        created = factory()
        cls.register(name, created)
        return created

    @classmethod
    def clear(cls, name: str | None = None) -> None:
        storage = cls._storage()
        if name is not None:
            storage.pop(name, None)
        else:
            storage.clear()
