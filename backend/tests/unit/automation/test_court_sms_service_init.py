def test_court_sms_service_init_builds_default_case_number_extractor():
    from apps.automation.services.sms.court_sms_service import CourtSMSService

    class _Fake:
        pass

    svc = CourtSMSService(
        case_service=_Fake(),
        document_processing_service=_Fake(),
        case_number_service=_Fake(),
        client_service=_Fake(),
        lawyer_service=_Fake(),
        case_chat_service=_Fake(),
    )
    assert svc.case_number_extractor is not None
