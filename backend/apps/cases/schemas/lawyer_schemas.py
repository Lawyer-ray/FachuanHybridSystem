"""API schemas and serializers."""

from __future__ import annotations

from typing import Protocol

from .base import Schema


class LawyerLike(Protocol):
    id: int
    username: str
    real_name: str | None
    phone: str | None


class LawyerOutFromDTO(Schema):
    id: int
    username: str
    real_name: str | None = None
    phone: str | None = None

    @classmethod
    def from_model(cls, lawyer: LawyerLike) -> LawyerOutFromDTO:
        return cls(
            id=lawyer.id,
            username=lawyer.username,
            real_name=getattr(lawyer, "real_name", None) or None,
            phone=getattr(lawyer, "phone", None) or None,
        )


__all__: list[str] = ["LawyerOutFromDTO"]
