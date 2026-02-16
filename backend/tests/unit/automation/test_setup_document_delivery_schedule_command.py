import io

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_setup_document_delivery_schedule_dry_run_does_not_delete_existing_schedule():
    from django_q.models import Schedule
    from django_q.tasks import schedule as q_schedule

    schedule_name = "document_delivery_periodic_check"
    q_schedule(
        "django.core.management.call_command",
        "execute_document_delivery_schedules",
        schedule_type="I",
        minutes=5,
        name=schedule_name,
        repeats=-1,
    )
    assert Schedule.objects.filter(name=schedule_name).count() == 1

    out = io.StringIO()
    call_command("setup_document_delivery_schedule", "--dry-run", "--name", schedule_name, stdout=out)

    assert Schedule.objects.filter(name=schedule_name).count() == 1
    assert "[DRY RUN]" in out.getvalue()


@pytest.mark.django_db
def test_setup_document_delivery_schedule_remove_dry_run_does_not_delete_existing_schedule():
    from django_q.models import Schedule
    from django_q.tasks import schedule as q_schedule

    schedule_name = "document_delivery_periodic_check"
    q_schedule(
        "django.core.management.call_command",
        "execute_document_delivery_schedules",
        schedule_type="I",
        minutes=5,
        name=schedule_name,
        repeats=-1,
    )
    assert Schedule.objects.filter(name=schedule_name).count() == 1

    out = io.StringIO()
    call_command("setup_document_delivery_schedule", "--dry-run", "--remove", "--name", schedule_name, stdout=out)

    assert Schedule.objects.filter(name=schedule_name).count() == 1
    assert "[DRY RUN]" in out.getvalue()

