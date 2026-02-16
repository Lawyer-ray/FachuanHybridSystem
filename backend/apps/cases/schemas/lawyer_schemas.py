"""API schemas and serializers."""

from typing import Any, Optional

from .base import Optional, Schema


class LawyerOutFromDTO(Schema):
    id: int
    username: str
    real_name: Optional[str] = None
    phone: Optional[str] = None

    @classmethod
    def from_model(cls, lawyer: Any) -> "LawyerOutFromDTO":
        return cls(
            id=lawyer.id,
            username=lawyer.username,
            real_name=getattr(lawyer, "real_name", None) or None,
            phone=getattr(lawyer, "phone", None) or None,
        )


__all__: list[str] = ["LawyerOutFromDTO"]
