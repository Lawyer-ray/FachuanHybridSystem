from django.core.files.uploadedfile import SimpleUploadedFile


def test_identity_recognize_submit_returns_task_id(client, monkeypatch):
    monkeypatch.setattr(
        "apps.client.api.clientidentitydoc_api.save_uploaded_file",
        lambda uploaded_file, rel_dir: ("tmp/identity_recognition/x.png", "x.png"),
    )
    monkeypatch.setattr(
        "apps.client.api.clientidentitydoc_api.submit_q_task",
        lambda *args, **kwargs: "t1",
    )

    f = SimpleUploadedFile("x.png", b"123", content_type="image/png")
    resp = client.post(
        "/api/v1/client/identity-doc/recognize/submit",
        data={"doc_type": "id_card", "file": f},
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "t1"
    assert data["status"] == "pending"


def test_identity_recognize_task_status_success(client, monkeypatch):
    monkeypatch.setattr(
        "apps.client.api.clientidentitydoc_api.get_q_task_status",
        lambda task_id: {
            "task_id": task_id,
            "status": "success",
            "result": {"doc_type": "id_card", "extracted_data": {"name": "a"}, "confidence": 0.9},
            "started_at": "x",
            "finished_at": "y",
        },
    )
    resp = client.get("/api/v1/client/identity-doc/task/t1", HTTP_HOST="localhost")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["result"]["doc_type"] == "id_card"
