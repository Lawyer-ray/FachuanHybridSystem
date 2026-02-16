"""API endpoints."""

from __future__ import annotations

from typing import Any, cast


def schema_to_update_dict(schema: Any) -> dict[str, Any]:
    if schema is None:
        return {}
    if isinstance(schema, dict):
        return schema
    model_dump = getattr(schema, "model_dump", None)
    if callable(model_dump):
        return cast(dict[str, Any], model_dump(exclude_unset=True))
    return cast(dict[str, Any], schema.dict(exclude_unset=True))
