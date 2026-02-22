"""
Contract Schemas - Client

客户相关的 Schema 定义.
"""

from __future__ import annotations

from apps.core.schemas_shared import ClientIdentityDocLiteOut as ClientIdentityDocOut
from apps.core.schemas_shared import ClientLiteOut as ClientOut

__all__: list[str] = ["ClientIdentityDocOut", "ClientOut"]
