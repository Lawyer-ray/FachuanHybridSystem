import pytest
from cryptography.fernet import Fernet
from django.conf import settings

from apps.core.models import SystemConfig
from apps.core.security.secret_codec import SecretCodec
from apps.core.services.system_config_service import SystemConfigService


@pytest.mark.django_db
def test_system_config_service_encrypts_secret_on_write_and_decrypts_on_read(monkeypatch):
    monkeypatch.setattr(settings, "SCRAPER_ENCRYPTION_KEY", Fernet.generate_key(), raising=False)

    service = SystemConfigService()
    service.set_value(key="SILICONFLOW_API_KEY", value="sk-test-token", category="llm", is_secret=True)

    row = SystemConfig.objects.get(key="SILICONFLOW_API_KEY")
    assert row.is_secret is True
    assert SecretCodec().is_encrypted(row.value) is True

    assert service.get_value("SILICONFLOW_API_KEY") == "sk-test-token"
