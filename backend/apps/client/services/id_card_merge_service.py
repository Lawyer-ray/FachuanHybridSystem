"""Business logic services."""

from .id_card_merge import IdCardMergeService as _IdCardMergeService


class IdCardMergeService(_IdCardMergeService):
    pass


__all__: list[str] = ["IdCardMergeService"]
