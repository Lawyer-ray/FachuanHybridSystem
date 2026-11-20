"""消息级律师反馈（点赞 / 点踩）。

前端 ``MessageActions`` 早就把按钮接上了，但后端一直没有对应路由——请求
404 回滚，律师看到的是「点了没反应」。反馈落在 ``AgentMessage.metadata``
的 ``rating`` 键上：走既有 JSONField，不加列、不加迁移。

``none`` 是**撤销**（删键），不是第三种态度：律师再点同一个按钮取消时，
库里不该继续留着「他曾经点过」的痕迹。

归属按**消息所属会话**判定，越权与不存在一律返回 ``None``（API 层转 404，
不是 403）——403 等于承认「这条消息存在」，是免费的存在性探测。
"""

from __future__ import annotations

from typing import Literal

from ..models import AgentMessage

#: 反馈取值：``up`` / ``down`` 落地，``none`` 表示撤销（删键）
Rating = Literal["up", "down", "none"]

#: ``AgentMessage.metadata`` 里的键名（历史回放读同一个键，只有一处拼写）
RATING_METADATA_KEY = "rating"


async def set_message_rating(*, message_id: int, user_id: int | None, rating: Rating) -> AgentMessage | None:
    """写入 / 撤销一条消息的律师反馈。

    ``user_id`` 为 ``None``（没有登录身份）时**什么也不匹配**，与
    ``session_service._scoped`` 同口径：无主会话只能由服务端内部代码访问。

    Returns:
        更新后的消息；消息不存在、或所属会话不属于当前律师时返回 ``None``。
    """
    if user_id is None:
        return None
    message = await AgentMessage.objects.filter(pk=message_id, session__user_id=user_id).afirst()
    if message is None:
        return None

    metadata = dict(message.metadata or {})
    if rating == "none":
        metadata.pop(RATING_METADATA_KEY, None)
    else:
        metadata[RATING_METADATA_KEY] = rating
    message.metadata = metadata
    await message.asave(update_fields=["metadata"])
    return message
