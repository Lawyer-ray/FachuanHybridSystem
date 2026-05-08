"""Calendar sync service — preview, deduplicate, and import calendar events."""

from __future__ import annotations

import logging
from datetime import datetime

from django.utils import timezone

from ..models import Reminder, ReminderType
from .calendar_providers import (
    CalendarEvent,
    get_available_providers,
    get_provider,
)

logger = logging.getLogger(__name__)


class CalendarSyncService:
    """Handle importing external calendar events into the Reminder system."""

    def get_available_providers(self) -> list[dict[str, str]]:
        """Return list of available provider metadata."""
        return get_available_providers()

    def preview_from_ics(self, ics_content: bytes) -> list[dict]:
        """Parse .ics content and return preview data with dedup markers."""
        provider = get_provider("ics")
        events = provider.fetch_events(ics_content=ics_content)
        return self._build_preview(events)

    def preview_from_url(self, url: str) -> list[dict]:
        """Download .ics from URL and return preview data."""
        provider = get_provider("ics_url")
        events = provider.fetch_events(url=url)
        return self._build_preview(events)

    def preview_from_local(self, provider_name: str, **kwargs: object) -> list[dict]:
        """Fetch events from a local provider (mac/windows) and return preview."""
        # Extract calendar filter params from kwargs
        excluded_calendars = kwargs.pop("excluded_calendars", None)
        included_calendars = kwargs.pop("included_calendars", None)
        provider = get_provider(provider_name)

        # Pass calendar filters to providers that support them
        fetch_kwargs = dict(kwargs)
        if included_calendars is not None and hasattr(provider, "DEFAULT_EXCLUDED_CALENDARS"):
            fetch_kwargs["included_calendars"] = included_calendars
        elif excluded_calendars is not None and hasattr(provider, "DEFAULT_EXCLUDED_CALENDARS"):
            fetch_kwargs["excluded_calendars"] = excluded_calendars

        events = provider.fetch_events(**fetch_kwargs)
        return self._build_preview(events)

    def import_events(self, events: list[dict]) -> tuple[int, int]:
        """Import selected events as Reminders. Returns (created_count, skipped_count)."""
        created = 0
        skipped = 0

        # Query current external_ids in DB for dedup
        existing_ids: set[str] = set(
            Reminder.objects.filter(metadata__has_key="external_id").values_list(
                "metadata__external_id", flat=True
            )
        )

        reminders_to_create: list[Reminder] = []
        for event_data in events:
            if not event_data.get("selected", False):
                continue

            external_id = event_data.get("uid", "")
            if external_id and external_id in existing_ids:
                skipped += 1
                continue

            kwargs = self._to_reminder_kwargs(event_data)
            reminder = Reminder(**kwargs)
            try:
                reminder.full_clean()
            except Exception as exc:
                logger.info("Skipping event %s: validation error %s", external_id, exc)
                skipped += 1
                continue

            reminders_to_create.append(reminder)
            if external_id:
                existing_ids.add(external_id)

        if reminders_to_create:
            Reminder.objects.bulk_create(reminders_to_create)
            created = len(reminders_to_create)

        logger.info("Calendar sync: created=%d, skipped=%d", created, skipped)
        return created, skipped

    def _build_preview(self, events: list[CalendarEvent]) -> list[dict]:
        """Convert CalendarEvent list to preview dicts, marking existing events."""
        existing_ids: set[str] = set(
            Reminder.objects.filter(metadata__has_key="external_id").values_list(
                "metadata__external_id", flat=True
            )
        )

        preview: list[dict] = []
        for event in events:
            start_str = ""
            end_str = ""
            if event.start_dt:
                start_str = timezone.localtime(event.start_dt).strftime("%Y-%m-%d %H:%M")
            if event.end_dt:
                end_str = timezone.localtime(event.end_dt).strftime("%Y-%m-%d %H:%M")

            is_existing = bool(event.uid and event.uid in existing_ids)

            preview.append(
                {
                    "uid": event.uid,
                    "title": event.title[:255] if event.title else "",
                    "start_dt": start_str,
                    "end_dt": end_str,
                    "location": event.location if event.location and event.location != "missing value" else "",
                    "description": event.description if event.description and event.description != "missing value" else "",
                    "organizer": event.organizer if event.organizer and event.organizer != "missing value" else "",
                    "calendar_name": event.calendar_name if event.calendar_name and event.calendar_name != "missing value" else "",
                    "is_all_day": event.is_all_day,
                    "is_existing": is_existing,
                }
            )

        return preview

    @staticmethod
    def _to_reminder_kwargs(event_data: dict) -> dict:
        """Convert a preview event dict to Reminder creation kwargs."""
        title = event_data.get("title", "")[:255]
        start_str = event_data.get("start_dt", "")

        due_at: datetime | None = None
        if start_str:
            try:
                naive = datetime.fromisoformat(start_str)
                due_at = timezone.make_aware(naive, timezone.get_current_timezone())
            except (ValueError, TypeError):
                pass

        if due_at is None:
            due_at = timezone.now()

        metadata: dict = {
            "source": "local_calendar_sync",
        }

        external_id = event_data.get("uid", "")
        if external_id:
            metadata["external_id"] = external_id

        calendar_name = event_data.get("calendar_name", "")
        if calendar_name and calendar_name != "missing value":
            metadata["calendar_name"] = calendar_name

        location = event_data.get("location", "")
        if location and location != "missing value":
            metadata["location"] = location

        description = event_data.get("description", "")
        if description and description != "missing value":
            metadata["note"] = description

        organizer = event_data.get("organizer", "")
        if organizer and organizer != "missing value":
            metadata["organizer"] = organizer

        return {
            "content": title,
            "reminder_type": ReminderType.OTHER,
            "due_at": due_at,
            "metadata": metadata,
        }
