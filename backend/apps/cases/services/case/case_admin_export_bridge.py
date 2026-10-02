"""Case admin export bridge helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from apps.cases.models import Case

_CASE_ADMIN_EXPORT_PREFETCHES: tuple[str, ...] = (
    "parties__client__identity_docs",
    "parties__client__property_clues__attachments",
    "assignments__lawyer",
    "supervising_authorities",
    "case_numbers",
    "chats",
    "logs__actor",
    "logs__attachments",
)

_CASE_ADMIN_FILE_PREFETCHES: tuple[str, ...] = (
    "parties__client__identity_docs",
    "parties__client__property_clues__attachments",
    "logs__attachments",
)


def get_case_admin_export_prefetches() -> tuple[str, ...]:
    """Return case-side prefetch paths needed by CaseAdmin export."""
    return _CASE_ADMIN_EXPORT_PREFETCHES


def get_case_admin_file_prefetches() -> tuple[str, ...]:
    """Return case-side prefetch paths needed by CaseAdmin file export."""
    return _CASE_ADMIN_FILE_PREFETCHES


def collect_case_file_paths_for_export(
    case: Case,
    add_path: Callable[[str], None],
) -> None:
    """Collect case-side file paths for admin export."""
    for party in case.parties.all():
        for identity_doc in party.client.identity_docs.all():
            add_path(identity_doc.file_path)
        for clue in party.client.property_clues.all():
            for attachment in clue.attachments.all():
                add_path(attachment.file_path)

    for log in case.logs.all():
        for attachment in log.attachments.all():
            if attachment.file:
                add_path(attachment.file.name)
