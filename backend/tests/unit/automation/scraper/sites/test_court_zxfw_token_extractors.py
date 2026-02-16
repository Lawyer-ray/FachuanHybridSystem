import pytest

from apps.automation.services.scraper.sites.court_zxfw_token_extractors import (
    extract_baoquan_token_from_authorization_json,
    extract_login_token_from_json,
    extract_token_from_url_query,
    is_hs512_jwt,
    is_jwt_like,
)


@pytest.mark.unit
def test_extract_token_from_url_query():
    url = "https://example.com/api/info?token=eyJhbGciOiJIUzUxMiJ9.abc.def&x=1"
    token = extract_token_from_url_query(url)
    assert token
    assert is_hs512_jwt(token)


@pytest.mark.unit
def test_extract_login_token_from_json_prefers_data_token():
    payload = {"data": {"token": "eyJ.a.b"}}
    assert extract_login_token_from_json(payload) == "eyJ.a.b"
    assert is_jwt_like("eyJ.a.b")


@pytest.mark.unit
def test_extract_login_token_from_json_falls_back_to_root_token():
    payload = {"token": "eyJ.c.d"}
    assert extract_login_token_from_json(payload) == "eyJ.c.d"


@pytest.mark.unit
def test_extract_baoquan_token_requires_hs512_prefix():
    assert extract_baoquan_token_from_authorization_json({"token": "eyJ.a.b"}) is None
    assert (
        extract_baoquan_token_from_authorization_json({"token": "eyJhbGciOiJIUzUxMiJ9.abc.def"})
        == "eyJhbGciOiJIUzUxMiJ9.abc.def"
    )
