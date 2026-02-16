"""Data parsing utilities."""

from datetime import datetime

from django.utils import timezone


def make_aware_if_needed(dt: datetime) -> datetime:
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
