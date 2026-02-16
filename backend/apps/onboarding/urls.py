"""Module for urls."""

from typing import Any

from django.urls import path

from . import views

app_name: str = "onboarding"

urlpatterns: list[Any] = [
    path("wizard/", views.wizard_view, name="wizard"),
]
