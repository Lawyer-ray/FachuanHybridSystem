from __future__ import annotations
from cryptography.fernet import Fernet
from django.conf import settings


from apps.core.model_fields.encrypted import EncryptedTextField


def test_encrypted_text_field_can_decrypt_with_previous_key(monkeypatch):
    field = EncryptedTextField()
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_KEY", old_key, raising=False)
    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_KEY_PREVIOUS", None, raising=False)
    enc_value = field.get_prep_value("hello")
    assert isinstance(enc_value, str)
    assert enc_value.startswith(field.prefix)

    field2 = EncryptedTextField()
    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_KEY", new_key, raising=False)
    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_KEY_PREVIOUS", old_key, raising=False)
    assert field2.to_python(enc_value) == "hello"
