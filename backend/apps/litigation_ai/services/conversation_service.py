"""Business logic services."""

from .conversation_session_service import LitigationConversationSessionService, MessageDTO, SessionDTO

ConversationService = LitigationConversationSessionService

__all__: list[str] = ["ConversationService", "LitigationConversationSessionService", "MessageDTO", "SessionDTO"]
