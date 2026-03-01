"""Module for routing."""

from typing import Any

from django.urls import path

from .consumers import LitigationConsumer
from .consumers.mock_trial_consumer import MockTrialConsumer

websocket_urlpatterns: list[Any] = [
    path("ws/litigation/sessions/<str:session_id>/", LitigationConsumer.as_asgi()),
    path("ws/mock-trial/sessions/<str:session_id>/", MockTrialConsumer.as_asgi()),
]
