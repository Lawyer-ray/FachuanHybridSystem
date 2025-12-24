import os
from pathlib import Path
import httpx


def _base_url() -> str:
    return (os.getenv("MOONSHOT_BASE_URL") or "https://api.moonshot.cn/v1").rstrip("/")


def _headers() -> dict:
    key = os.getenv("MOONSHOT_API_KEY")
    return {"Authorization": f"Bearer {key}"}


def upload_file(file_path: str) -> dict:
    url = _base_url() + "/files"
    p = Path(file_path)
    with p.open("rb") as f:
        files = {"file": (p.name, f)}
        with httpx.Client(timeout=60) as client:
            resp = client.post(url, headers=_headers(), files=files)
            resp.raise_for_status()
            return resp.json()


def list_files() -> dict:
    url = _base_url() + "/files"
    with httpx.Client(timeout=60) as client:
        resp = client.get(url, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def retrieve_file(file_id: str) -> dict:
    url = _base_url() + f"/files/{file_id}"
    with httpx.Client(timeout=60) as client:
        resp = client.get(url, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def extract_result(file_id: str) -> dict:
    url = _base_url() + f"/files/{file_id}/extraction"
    with httpx.Client(timeout=60) as client:
        resp = client.get(url, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def chat(model: str, messages: list[dict]) -> dict:
    url = _base_url() + "/chat/completions"
    payload = {"model": model, "messages": messages}
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers={"Authorization": _headers()["Authorization"]}, json=payload)
        resp.raise_for_status()
        return resp.json()
