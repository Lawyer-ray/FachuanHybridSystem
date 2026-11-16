"""模型向律师提问的回答契约。"""

from __future__ import annotations

from ninja import Schema


class QuestionAnswerItem(Schema):
    """单个问题的回答。

    按 ``id`` 回填而不是下标：前端可能只答一部分或顺序错乱，按 id 对齐
    才不会出现「答的是第 2 题被当成第 1 题」的静默错位——法律场景里
    问错一次比不问更糟。
    """

    id: str
    selections: list[str] = []
    text: str = ""
    comment: str = ""


class QuestionAnswerIn(Schema):
    """前端提交提问回答。"""

    answers: list[QuestionAnswerItem] = []
    #: 律师主动跳过（与「超时没看到」不同，要如实区分）
    skipped: bool = False
