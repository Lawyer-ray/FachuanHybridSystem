from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from apps.legal_research.models import LegalResearchTaskEvent

logger = logging.getLogger(__name__)


class LegalResearchTaskEventService:
    MAX_ERROR_MESSAGE_CHARS = 255
    MAX_URL_CHARS = 1000
    MAX_STRING_CHARS = 420
    MAX_DICT_ITEMS = 32
    MAX_LIST_ITEMS = 24
    MAX_TOTAL_PAYLOAD_CHARS = 2200
    MASKED_VALUE = "***"
    SENSITIVE_KEYWORDS = (
        "password",
        "passwd",
        "secret",
        "token",
        "authorization",
        "cookie",
        "api_key",
        "apikey",
        "key",
        "ticket",
        "signature",
        "sign",
        "username",
        "account",
    )

    @classmethod
    def record_event(
        cls,
        *,
        task_id: object,
        stage: str,
        source: str,
        interface_name: str,
        method: str = "",
        url: str = "",
        status_code: int | None = None,
        duration_ms: int = 0,
        success: bool = True,
        error_code: str = "",
        error_message: str = "",
        request_summary: object = None,
        response_summary: object = None,
        event_metadata: object = None,
    ) -> None:
        normalized_task_id = cls._normalize_task_id(task_id)
        if normalized_task_id is None:
            return

        try:
            LegalResearchTaskEvent.objects.create(
                task_id=normalized_task_id,
                stage=cls._normalize_stage(stage),
                source=cls._normalize_source(source),
                interface_name=str(interface_name or "").strip()[:64] or "unknown",
                method=str(method or "").strip().upper()[:12],
                url=cls._sanitize_url(url),
                status_code=cls._normalize_status_code(status_code),
                duration_ms=max(0, int(duration_ms or 0)),
                success=bool(success),
                error_code=str(error_code or "").strip()[:64],
                error_message=str(error_message or "").strip()[: cls.MAX_ERROR_MESSAGE_CHARS],
                request_summary=cls._sanitize_payload(request_summary),
                response_summary=cls._sanitize_payload(response_summary),
                event_metadata=cls._sanitize_payload(event_metadata),
            )
        except Exception:
            logger.exception(
                "写入法律检索事件失败",
                extra={
                    "task_id": normalized_task_id,
                    "stage": stage,
                    "source": source,
                    "interface_name": interface_name,
                },
            )

    @staticmethod
    def _normalize_task_id(task_id: object) -> int | None:
        raw = str(task_id or "").strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @classmethod
    def _normalize_stage(cls, stage: str) -> str:
        normalized = str(stage or "").strip().lower()
        allowed = {choice for choice, _ in LegalResearchTaskEvent.Stage.choices}
        return normalized if normalized in allowed else LegalResearchTaskEvent.Stage.SEARCH

    @classmethod
    def _normalize_source(cls, source: str) -> str:
        normalized = str(source or "").strip().lower()
        allowed = {choice for choice, _ in LegalResearchTaskEvent.Source.choices}
        return normalized if normalized in allowed else LegalResearchTaskEvent.Source.SYSTEM

    @staticmethod
    def _normalize_status_code(value: object) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        if parsed < 100 or parsed > 999:
            return None
        return parsed

    @classmethod
    def _sanitize_url(cls, url: str) -> str:
        text = str(url or "").strip()
        if not text:
            return ""
        text = re.sub(r"(?i)(password|token|ticket|signature|api[_-]?key)=([^&]+)", rf"\1={cls.MASKED_VALUE}", text)
        if len(text) <= cls.MAX_URL_CHARS:
            return text
        return f"{text[: cls.MAX_URL_CHARS - 3]}..."

    @classmethod
    def _sanitize_payload(cls, value: object) -> dict[str, Any]:
        sanitized = cls._sanitize_node(value=value, level=0, key_hint="")
        if isinstance(sanitized, Mapping):
            payload: dict[str, Any] = {str(k): v for k, v in sanitized.items()}
        elif sanitized in ("", None):
            payload = {}
        else:
            payload = {"value": sanitized}

        serialized = json.dumps(payload, ensure_ascii=False, default=str)
        if len(serialized) <= cls.MAX_TOTAL_PAYLOAD_CHARS:
            return payload

        clipped = serialized[: cls.MAX_TOTAL_PAYLOAD_CHARS - 3] + "..."
        return {"preview": clipped}

    @classmethod
    def _sanitize_node(cls, *, value: object, level: int, key_hint: str) -> object:
        if level > 4:
            return "..."

        if value is None:
            return None

        if isinstance(value, Mapping):
            out: dict[str, Any] = {}
            for idx, (k, v) in enumerate(value.items()):
                if idx >= cls.MAX_DICT_ITEMS:
                    out["__truncated__"] = True
                    break
                key = str(k or "")[:64]
                if cls._is_sensitive_key(key):
                    out[key] = cls.MASKED_VALUE
                    continue
                out[key] = cls._sanitize_node(value=v, level=level + 1, key_hint=key)
            return out

        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            out_list: list[Any] = []
            for idx, item in enumerate(value):
                if idx >= cls.MAX_LIST_ITEMS:
                    out_list.append("...")
                    break
                out_list.append(cls._sanitize_node(value=item, level=level + 1, key_hint=key_hint))
            return out_list

        if isinstance(value, bytes):
            return f"<bytes:{len(value)}>"

        text = str(value)
        if cls._is_sensitive_key(key_hint):
            return cls.MASKED_VALUE
        if len(text) <= cls.MAX_STRING_CHARS:
            return text
        return f"{text[: cls.MAX_STRING_CHARS - 3]}..."

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        normalized = re.sub(r"[^a-z0-9_]+", "", (key or "").lower())
        if not normalized:
            return False
        return any(token in normalized for token in cls.SENSITIVE_KEYWORDS)
