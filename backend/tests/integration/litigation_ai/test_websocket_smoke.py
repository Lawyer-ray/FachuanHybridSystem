from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser

from apps.litigation_ai.routing import websocket_urlpatterns


@pytest.mark.anyio
async def test_ws_anonymous_rejected_and_user_accepted():
    application = URLRouter(websocket_urlpatterns)

    anon = WebsocketCommunicator(application, "/ws/litigation/sessions/s1/")
    anon.scope["user"] = AnonymousUser()
    connected, _ = await anon.connect()
    assert connected is False

    with patch(
        "apps.litigation_ai.services.conversation_flow_service.ConversationFlowService.handle_init",
        new=AsyncMock(return_value=None),
    ):
        with patch(
            "apps.litigation_ai.consumers.litigation_consumer.LitigationConsumer._get_session",
            new=AsyncMock(return_value=SimpleNamespace(case_id=1)),
        ):
            authed = WebsocketCommunicator(application, "/ws/litigation/sessions/s1/")
            authed.scope["user"] = SimpleNamespace(id=1)
            connected2, _ = await authed.connect()
            assert connected2 is True
            await authed.disconnect()
