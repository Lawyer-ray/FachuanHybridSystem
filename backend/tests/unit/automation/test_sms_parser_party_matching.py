from apps.automation.services.sms.parsing import PartyCandidateExtractor
from apps.automation.services.sms.sms_parser_service import SMSParserService


class _Client:
    def __init__(self, name: str):
        self.name = name


class _FakePartyMatchingService:
    def __init__(self, clients):
        self.clients = clients
        self.last_candidates = None

    def extract_and_match_parties_from_sms(self, party_names):
        self.last_candidates = list(party_names or [])
        return list(self.clients or [])


def test_party_candidate_extractor_extracts_receiver_and_companies():
    extractor = PartyCandidateExtractor()
    content = "【佛山市禅城区人民法院】佛山市升平百货有限公司，（2025）粤0604民初42953号你有通知"
    out = extractor.extract(content)
    assert "佛山市升平百货有限公司" in out


def test_sms_parser_extract_party_names_uses_party_matching_service_results():
    fake = _FakePartyMatchingService(clients=[_Client("佛山市升平百货有限公司")])
    svc = SMSParserService(party_matching_service=fake, party_candidate_extractor=PartyCandidateExtractor())
    content = "【佛山市禅城区人民法院】佛山市升平百货有限公司，（2025）粤0604民初42953号你有通知"
    names = svc.extract_party_names(content)
    assert names == ["佛山市升平百货有限公司"]
    assert fake.last_candidates is not None and len(fake.last_candidates) > 0
