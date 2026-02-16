import apps.automation.workers.court_sms_tasks as tasks
from apps.automation.services.sms import court_sms_service


def test_process_sms_async_delegates_to_workers(monkeypatch):
    def fake_process_sms(sms_id: int):
        return {"sms_id": sms_id}

    monkeypatch.setattr(tasks, "process_sms", fake_process_sms)
    assert court_sms_service.process_sms_async(123) == {"sms_id": 123}


def test_retry_download_task_delegates_to_workers(monkeypatch):
    captured = {}

    def fake_retry(sms_id, **kwargs):
        captured["sms_id"] = sms_id
        captured["kwargs"] = kwargs
        return "ok"

    monkeypatch.setattr(tasks, "retry_download_task", fake_retry)
    assert court_sms_service.retry_download_task("456", foo="bar") == "ok"
    assert captured["sms_id"] == "456"
    assert captured["kwargs"] == {"foo": "bar"}
