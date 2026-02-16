import pytest
from django.test import Client
from django.test.utils import override_settings


@pytest.mark.django_db
@pytest.mark.unit
@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
def test_liveness_probe_has_zero_db_queries(django_assert_num_queries):
    client = Client()
    with django_assert_num_queries(0):
        response = client.get("/api/v1/health/live")
    assert response.status_code == 200
