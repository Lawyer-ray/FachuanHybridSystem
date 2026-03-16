from __future__ import annotations

from apps.automation.services.sms.sms_parser_service import SMSParserService


class _NoopMatcher:
    def extract_and_match_parties_from_sms(self, party_names):
        return []


class _NoopExtractor:
    def extract(self, content):
        return []


def test_sms_parser_init_does_not_eagerly_load_ollama_config(monkeypatch) -> None:
    calls = {"model": 0, "base_url": 0}

    def _fake_model() -> str:
        calls["model"] += 1
        return "fake-model"

    def _fake_base_url() -> str:
        calls["base_url"] += 1
        return "http://fake-ollama.local"

    monkeypatch.setattr("apps.automation.services.sms.sms_parser_service.get_ollama_model", _fake_model)
    monkeypatch.setattr("apps.automation.services.sms.sms_parser_service.get_ollama_base_url", _fake_base_url)

    svc = SMSParserService(
        party_matching_service=_NoopMatcher(),
        party_candidate_extractor=_NoopExtractor(),
    )

    assert calls == {"model": 0, "base_url": 0}
    assert svc.ollama_model == "fake-model"
    assert svc.ollama_base_url == "http://fake-ollama.local"
    assert calls == {"model": 1, "base_url": 1}
