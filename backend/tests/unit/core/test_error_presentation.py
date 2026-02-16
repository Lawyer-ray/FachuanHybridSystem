from apps.core.error_presentation import ExceptionPresenter
from apps.core.exceptions import BusinessError, ValidationException


def test_present_validation_exception_http():
    presenter = ExceptionPresenter()
    envelope, status = presenter.present(ValidationException(message="x", code="VALIDATION_ERROR"), channel="http", debug=True)
    assert status == 400
    payload = envelope.to_payload()
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["message"] == "x"
    assert payload["error"] == "x"


def test_present_generic_exception_non_debug_http():
    presenter = ExceptionPresenter()
    envelope, status = presenter.present(RuntimeError("boom"), channel="http", debug=False)
    assert status == 500
    payload = envelope.to_payload()
    assert payload["code"] == "INTERNAL_ERROR"
    assert payload["message"] != "boom"


def test_present_business_error_uses_explicit_status():
    presenter = ExceptionPresenter()
    envelope, status = presenter.present(BusinessError(message="x", code="X", status=503), channel="http", debug=True)
    assert status == 503
    payload = envelope.to_payload()
    assert payload["code"] == "X"
