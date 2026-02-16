"""Business logic services."""

from django.db.models import QuerySet

from apps.cases.models import Case


def get_case_queryset() -> QuerySet[Case, Case]:
    return Case.objects.select_related(
        "contract",
    ).prefetch_related(
        "parties__client",
        "assignments__lawyer",
        "assignments__lawyer__law_firm",
        "logs__attachments",
        "case_numbers",
        "supervising_authorities",
        "contract__supplementary_agreements__parties__client",
    )
