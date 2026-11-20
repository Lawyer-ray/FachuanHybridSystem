"""非法 ``session_id`` 必须是 404，不是 500。

## 来历（真机实测，不是假想）

合并 B2 后对运行中的后端发了一次：

    POST /api/v1/agent/sessions/nope/review   →  500 INTERNAL_ERROR

日志里的堆栈是 ``ValidationError: “nope”不是一个有效的UUID``——``AgentSession.session_id``
是 ``UUIDField``，Django 在**查询构造阶段**就会抛异常，根本到不了"查不到"那一支。
而对该端点、以及所有走 ``get_session`` 的会话端点来说，「id 不合法」与
「id 不存在」对调用方是同一件事：**都应该 404**。

修法在 ``session_service._as_uuid``：先宽松转 UUID，转不了返回 ``None``。
这样 ``get_session`` 对垃圾 id 返回 ``None``，上层照常走 404 分支。
"""

from __future__ import annotations

import uuid

import pytest

from apps.agent.services.session_service import _as_uuid, get_session


class TestAsUuid:
    def test_accepts_uuid_object_and_canonical_string(self) -> None:
        value = uuid.uuid4()
        assert _as_uuid(value) == value
        assert _as_uuid(str(value)) == value

    @pytest.mark.parametrize("bad", ["nope", "", "  ", "123", None, 12345, object()])
    def test_rejects_garbage_without_raising(self, bad: object) -> None:
        """任何怪输入都只返回 None——这里抛一次异常，线上就是一个 500。"""
        assert _as_uuid(bad) is None


class TestGetSessionWithBadId:
    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_garbage_id_returns_none_instead_of_raising(self) -> None:
        assert await get_session(session_id="nope", user_id=None) is None

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_absent_but_valid_uuid_returns_none(self) -> None:
        assert await get_session(session_id="00000000-0000-0000-0000-000000000000", user_id=None) is None
