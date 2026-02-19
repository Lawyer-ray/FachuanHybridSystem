"""Business logic services."""

import json
from typing import Any

from apps.core.path import Path


class CookieService:
    def __init__(self, storage_path: str | None = None) -> None:
        self.storage_path = storage_path

    def load(self, context: Any, storage_path: str | None = None) -> bool:
        path = storage_path or self.storage_path
        if not path:
            return False
        p = Path(path)
        if not p.exists():
            return False
        data = json.loads(p.read_text(encoding="utf-8"))
        cookies = data.get("cookies") if isinstance(data, dict) else None
        if not cookies:
            return False
        context.add_cookies(cookies)
        return True

    def save(self, context: Any, storage_path: str | None = None) -> str:
        path = storage_path or self.storage_path
        if not path:
            raise ValueError("storage_path is required")
        p = Path(path)
        p.parent.makedirs_p()
        context.cookies()
        payload = ({},)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(p)
