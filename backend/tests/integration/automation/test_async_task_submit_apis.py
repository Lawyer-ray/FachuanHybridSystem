import json


def test_document_delivery_query_submits_task(client, monkeypatch):
    monkeypatch.setattr(
        "apps.automation.api.document_delivery_api.submit_q_task",
        lambda *args, **kwargs: "t-doc",
    )
    resp = client.post(
        "/api/v1/automation/document-delivery/query",
        data=json.dumps({"credential_id": 1, "cutoff_hours": 24, "tab": "pending"}),
        content_type="application/json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["task_id"] == "t-doc"


def test_document_processor_submit_returns_task(client, monkeypatch):
    monkeypatch.setattr(
        "apps.automation.api.document_processor_api.submit_q_task",
        lambda *args, **kwargs: "t-proc",
    )
    resp = client.post(
        "/api/v1/automation/document-processor/process/submit",
        data=json.dumps({"file_path": "/tmp/a.pdf", "kind": "pdf", "limit": 10, "preview_page": 1}),
        content_type="application/json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    assert resp.json()["task_id"] == "t-proc"


def test_auto_namer_submit_by_path_returns_task(client, monkeypatch):
    monkeypatch.setattr(
        "apps.automation.api.auto_namer_api.submit_q_task",
        lambda *args, **kwargs: "t-namer",
    )
    resp = client.post(
        "/api/v1/automation/auto-namer/process-by-path/submit",
        data=json.dumps({"file_path": "/tmp/a.pdf", "prompt": "p", "model": "m", "limit": None, "preview_page": None}),
        content_type="application/json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    assert resp.json()["task_id"] == "t-namer"
