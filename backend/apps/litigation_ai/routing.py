"""Module for routing."""

from typing import Any

from django.urls import path

from .consumers import LitigationConsumer

websocket_urlpatterns: list[Any] = [
    path("ws/litigation/sessions/<str:session_id>/", LitigationConsumer.as_asgi()),
]
