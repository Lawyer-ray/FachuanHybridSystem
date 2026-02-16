import pytest
from django.utils import timezone

from apps.automation.models import TokenAcquisitionHistory, TokenAcquisitionStatus
from apps.core.security.scrub import fingerprint_sha256, mask_secret


@pytest.mark.django_db
def test_token_acquisition_history_scrubs_preview_and_error_details_on_save():
    preview = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.VERYLONGTOKENVALUE"
    record = TokenAcquisitionHistory.objects.create(
        site_name="court_zxfw",
        account="test_account",
        credential_id=1,
        status=TokenAcquisitionStatus.FAILED,
        trigger_reason="test",
        attempt_count=1,
        total_duration=1.0,
        token_preview=preview,
        error_message=f"Authorization: Bearer {preview}",
        error_details={
            "authorization": f"Bearer {preview}",
            "token": preview,
            "nested": {"api_key": "sk-ABCDEFGHIJKLMN1234567890"},
        },
        created_at=timezone.now(),
        started_at=timezone.now(),
        finished_at=timezone.now(),
    )

    record.refresh_from_db()

    assert record.token_preview is None
    assert record.token_redacted == mask_secret(preview)
    assert record.token_fingerprint == fingerprint_sha256(preview)

    assert record.error_details["authorization"] == "***"
    assert record.error_details["token"] == "***"
    assert record.error_details["nested"]["api_key"] == "***"
    assert "***" in record.error_message
    assert preview not in record.error_message
