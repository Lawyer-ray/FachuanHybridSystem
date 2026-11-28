"""真机 UI 动作冒烟的公用车床：探活、HTTP、MCP、造包、读审计。

## 为什么只依赖标准库

本文件与 ``ui_action_smoke.py`` 要能在**没有 Django settings**的进程里跑（playwright
也只在后端 venv 里有）。Django 只出现在 :func:`_mint_token` 的子进程里——
不是为了省依赖，而是因为主进程一旦 ``django.setup()``，就会把启动期迁移健康检查
一起拉起来；那项检查在「迁移图还没合全」的 worktree 里会直接抛
``NodeNotFoundError``，而铸一张票本身只需要 ORM 与用户表。

token / 密码一律不打印、不写文件：HTTP 头只在内存里拼，唯一的跨进程传递是
子进程 stdout 上的一行标记（父进程解析后立刻丢弃原始输出）。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: 仓库根目录（scripts/e2e/common.py → scripts/e2e → scripts → 仓库根）
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

FRONTEND_BASE = "http://127.0.0.1:5090"
BACKEND_BASE = "http://127.0.0.1:8002"
MCP_ENDPOINT = "http://127.0.0.1:8011/mcp"

#: 前置服务清单（端口号是 CLI 输出的一部分，名字只用于提示）。
SERVICES: tuple[tuple[str, int], ...] = (
    ("前端 dev server", 5090),
    ("Django", 8002),
    ("共享 MCP", 8011),
)

#: 上传附件的内容与扩展名：``.txt`` 在收件箱白名单内，且不会触发 PDF 页数解析。
UPLOAD_BODY = "fachuan e2e ui-action smoke fixture\n"


class E2eError(RuntimeError):
    """脚本可预期的失败（带一句人能读的原因，不携带 token）。"""


def out(*parts: object) -> None:
    """命令行输出统一出口。

    为什么不用 print：本仓的日志纪律是「生产代码用 logger」；CLI 工具的结果必须
    直接可见，所以统一走这里（与 ``scripts/e2e_home.py`` 同一写法）。
    """
    sys.stdout.write(" ".join(str(part) for part in parts) + "\n")
    sys.stdout.flush()


def probe_services(timeout: float = 1.0) -> list[tuple[str, int, bool]]:
    """逐个探 TCP 端口，返回 ``[(名字, 端口, 是否可达)]``。

    只探连通性、不发 HTTP：5090 的前端根路径可能 200、8002 的根路径是 404，
    用状态码判定会把「服务活着」误判成「服务挂了」。
    """
    rows: list[tuple[str, int, bool]] = []
    for name, port in SERVICES:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout):
                ready = True
        except OSError:
            ready = False
        rows.append((name, port, ready))
    return rows


@dataclass(frozen=True)
class HttpResponse:
    """一次 HTTP 往返的原始结果（状态码 + 文本体）。"""

    status: int
    body: str

    def json_dict(self) -> dict[str, Any]:
        """按 JSON 对象解析；形状不对就按「契约漂移」报错，而不是返回空 dict。"""
        try:
            data: Any = json.loads(self.body or "{}")
        except json.JSONDecodeError as exc:
            raise E2eError(f"响应不是 JSON（status={self.status}）：{self.body[:300]}") from exc
        if not isinstance(data, dict):
            raise E2eError(f"响应不是 JSON 对象（status={self.status}）：{self.body[:300]}")
        return data


def http_request(
    method: str,
    url: str,
    *,
    token: str = "",
    body: dict[str, Any] | None = None,
    raw: bytes | None = None,
    content_type: str = "",
    timeout: float = 60.0,
) -> HttpResponse:
    """发一次 HTTP 请求，HTTP 错误也按普通响应返回（调用方自己判状态码）。"""
    headers: dict[str, str] = {"Accept": "application/json"}
    data: bytes | None = None
    if raw is not None:
        data = raw
        if content_type:
            headers["Content-Type"] = content_type
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # URL 只来自本文件的端点常量（或 BACKEND_BASE + 固定 path），不接受外部输入。
    request = urllib.request.Request(url, data=data, headers=headers, method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL 只来自本文件常量
            return HttpResponse(response.status, response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code, exc.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise E2eError(f"{method} {url} 连不上：{exc}") from exc


def api(
    token: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    raw: bytes | None = None,
    content_type: str = "",
    timeout: float = 60.0,
) -> HttpResponse:
    """对 Django API（:8002）发一次请求；``path`` 以 ``/api/v1`` 开头。"""
    return http_request(
        method,
        f"{BACKEND_BASE}{path}",
        token=token,
        body=body,
        raw=raw,
        content_type=content_type,
        timeout=timeout,
    )


@dataclass(frozen=True)
class Credential:
    """一张律师身份票 + 它从哪来（token 本身不参与 repr / 不打印）。"""

    token: str = field(repr=False)
    source: str
    username: str = ""


def _mint_python() -> Path:
    """铸票子进程用的解释器：优先后端 venv，其次当前解释器。

    本脚本由 Makefile 用 ``backend/.venv/bin/python`` 启动，正常情况下两者同一个；
    退到 ``sys.executable`` 只为「有人用系统 python 直接跑」时给一句可执行的错。
    """
    candidate = BACKEND_DIR / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else Path(sys.executable)


#: 子进程脚本：只做「取一个启用用户 + 铸一张 access token」。
#:
#: ``sys.argv`` 里塞 ``test`` 是刻意的：``apps.core.apps.ready()`` 用同一个字符串
#: 跳过启动期迁移健康检查。那次检查会构造 MigrationExecutor，在迁移图尚未合全的
#: worktree 里会抛 ``NodeNotFoundError``；而铸票只需要 ORM，不该被无关检查拦住。
_MINT_SOURCE = """
import json
import os
import sys

sys.argv = ["fachuan-e2e-token-mint", "test"]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

import django

django.setup()

from django.contrib.auth import get_user_model

from apps.agent.pi.user_token import mint_user_access_token

user_model = get_user_model()
raw_user_id = os.environ.get("FACHUAN_E2E_USER_ID", "").strip()
raw_username = os.environ.get("FACHUAN_E2E_USERNAME", "").strip()
if raw_user_id:
    user = user_model.objects.get(pk=int(raw_user_id))
elif raw_username:
    user = user_model.objects.get(username=raw_username)
else:
    user = user_model.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
    if user is None:
        user = user_model.objects.filter(is_active=True).order_by("pk").first()
if user is None:
    raise SystemExit("数据库里没有可用用户（先建一个启用的律师账号）")

token = mint_user_access_token(user.pk)
sys.stdout.write(
    "\\nFACHUAN_E2E_MINT="
    + json.dumps({"token": token, "username": user.get_username(), "user_id": user.pk}, ensure_ascii=False)
    + "\\n"
)
"""

_MINT_MARKER = "FACHUAN_E2E_MINT="


def _mint_token() -> Credential:
    """用 Django 现场铸一张票（子进程）。失败信息只带 stderr 尾部，从不带 stdout。"""
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "apiSystem.settings"
    env["PYTHONPATH"] = os.pathsep.join(["apiSystem", "."])
    env.pop("PYTHONHOME", None)
    try:
        completed = subprocess.run(
            [str(_mint_python()), "-c", _MINT_SOURCE],
            cwd=str(BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise E2eError(f"Django 铸 token 子进程起不来：{exc}") from exc

    marker_line = next(
        (line for line in completed.stdout.splitlines() if line.startswith(_MINT_MARKER)),
        "",
    )
    if completed.returncode != 0 or not marker_line:
        stderr_tail = "\n".join(completed.stderr.strip().splitlines()[-8:])
        detail = stderr_tail or f"rc={completed.returncode}，stdout 里没有铸票标记"
        raise E2eError(
            "Django 铸 token 失败。先确认后端依赖/数据库可用（或直接设 FACHUAN_E2E_TOKEN）：\n" + detail
        )
    try:
        payload: Any = json.loads(marker_line[len(_MINT_MARKER) :])
    except json.JSONDecodeError as exc:
        raise E2eError("铸票子进程输出无法解析（不是 token 本身的问题）") from exc
    if not isinstance(payload, dict):
        raise E2eError("铸票子进程输出形状不对")
    token = str(payload.get("token") or "")
    if not token:
        raise E2eError("铸票子进程没有返回 access token")
    return Credential(token=token, source="django-mint", username=str(payload.get("username") or ""))


def resolve_credential() -> Credential:
    """取律师身份票：优先 ``FACHUAN_E2E_TOKEN``，否则现场用 Django 铸一张。"""
    env_token = os.environ.get("FACHUAN_E2E_TOKEN", "").strip()
    if env_token:
        return Credential(token=env_token, source="env:FACHUAN_E2E_TOKEN")
    return _mint_token()


def create_session(token: str, title: str) -> str:
    """建一个专用会话（跑完由调用方删除），返回 ``session_id``。"""
    response = api(token, "POST", "/api/v1/agent/sessions", body={"title": title, "origin": "chat"})
    if response.status != 200:
        raise E2eError(f"建会话失败 status={response.status} body={response.body[:300]}")
    session_id = str(response.json_dict().get("session_id") or "")
    if not session_id:
        raise E2eError(f"建会话返回里没有 session_id：{response.body[:300]}")
    return session_id


def delete_session(token: str, session_id: str) -> bool:
    """删会话；返回是否真的删掉（404 也算「已经不在了」）。"""
    response = api(token, "DELETE", f"/api/v1/agent/sessions/{session_id}")
    if response.status in (200, 204):
        return True
    if response.status == 404:
        return False
    raise E2eError(f"删会话失败 status={response.status} body={response.body[:300]}")


def upload_pack(token: str, subject: str) -> dict[str, Any]:
    """上传一个专用材料包（单文件 multipart），返回上传接口的 JSON。

    ``subject`` 由调用方保证带 ``E2E-`` 前缀；文件名也用同一个 subject，便于事后
    在收件箱里一眼认出这是脚本造的数据。
    """
    boundary = f"----fachuan-e2e-{uuid.uuid4().hex}"
    chunks = [
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="subject"\r\n\r\n'
            f"{subject}\r\n"
        ).encode(),
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="'
            f'{subject}.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
            f"{UPLOAD_BODY}\r\n"
        ).encode(),
        f"--{boundary}--\r\n".encode(),
    ]
    response = api(
        token,
        "POST",
        "/api/v1/inbox/messages/upload",
        raw=b"".join(chunks),
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    if response.status != 201:
        raise E2eError(f"上传材料包失败 status={response.status} body={response.body[:300]}")
    payload = response.json_dict()
    if not isinstance(payload.get("id"), int):
        raise E2eError(f"上传返回里没有整数 id：{response.body[:300]}")
    return payload


def get_pack(token: str, pack_id: int) -> dict[str, Any] | None:
    """读材料包详情；``404`` 返回 ``None``（删除链路的正向断言就靠它）。"""
    response = api(token, "GET", f"/api/v1/inbox/messages/{pack_id}")
    if response.status == 404:
        return None
    if response.status != 200:
        raise E2eError(f"读材料包 {pack_id} 失败 status={response.status} body={response.body[:300]}")
    return response.json_dict()


def delete_pack(token: str, pack_id: int) -> bool:
    """删材料包；返回是否真的删掉（404 也算已不在）。"""
    response = api(token, "DELETE", f"/api/v1/inbox/messages/{pack_id}")
    if response.status in (200, 204):
        return True
    if response.status == 404:
        return False
    raise E2eError(f"删材料包 {pack_id} 失败 status={response.status} body={response.body[:300]}")


def pack_status(pack: dict[str, Any]) -> str:
    """材料包状态 = ``draft_state["status"]``（与核实器 ``material_prep_status`` 同源）。"""
    draft = pack.get("draft_state")
    if not isinstance(draft, dict):
        return ""
    return str(draft.get("status") or "")


def pack_fingerprint(pack: dict[str, Any]) -> dict[str, Any]:
    """「零变化」的比较口径：只看动作会改的业务字段，不看 ``read_at`` 之类的页内态。"""
    return {
        "subject": str(pack.get("subject") or ""),
        "has_attachments": bool(pack.get("has_attachments")),
        "attachment_count": int(pack.get("attachment_count") or 0),
        "draft_state": pack.get("draft_state") or {},
    }


def list_ui_actions(token: str, limit: int = 200) -> list[dict[str, Any]]:
    """当前用户的 UI 动作审计历史（新 → 旧）；只保留对象行。"""
    response = api(token, "GET", f"/api/v1/agent/ui-actions?limit={limit}")
    if response.status != 200:
        raise E2eError(f"读审计台账失败 status={response.status} body={response.body[:300]}")
    items = response.json_dict().get("items")
    if not isinstance(items, list):
        raise E2eError("审计台账返回里没有 items 列表")
    return [item for item in items if isinstance(item, dict)]


def _parse_jsonrpc(raw: str) -> dict[str, Any]:
    """解析 MCP 应答：streamable-http 可能回 SSE（``data: {...}``），也可能回纯 JSON。"""
    text = raw.strip()
    data: Any = None
    if text.startswith("{"):
        data = json.loads(text)
    else:
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk.startswith("{"):
                data = json.loads(chunk)
                break
    if not isinstance(data, dict):
        raise E2eError(f"无法解析 MCP 应答：{raw[:400]}")
    error = data.get("error")
    if error is not None:
        raise E2eError(f"MCP 返回错误：{json.dumps(error, ensure_ascii=False)[:300]}")
    return data


def _mcp_post(
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, dict[str, str], str]:
    """POST 一帧到 MCP；HTTP 错误转换成带方法名的 E2eError。"""
    request = urllib.request.Request(
        MCP_ENDPOINT,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - 端点常量
            return (
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                response.read().decode("utf-8", "replace"),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise E2eError(f"MCP HTTP {exc.code}（{payload.get('method')}）：{body[:300]}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise E2eError(f"MCP 连不上（{payload.get('method')}）：{exc}") from exc


def call_mcp_tool(
    token: str,
    session_id: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    timeout: float = 240.0,
) -> dict[str, Any]:
    """按 MCP streamable-http 的规矩真调一次工具，返回 JSON-RPC 的 ``result``。

    握手与 pi 子进程完全一致：``Authorization: Bearer <律师 token>`` 让工具以律师
    本人身份执行；``x-fachuan-session`` 让审批闸门知道这张卡该弹给哪个会话。
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
        "x-fachuan-session": session_id,
    }
    _, response_headers, raw = _mcp_post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "fachuan-e2e-ui-action", "version": "0"},
            },
        },
        headers,
        timeout=60.0,
    )
    _parse_jsonrpc(raw)
    mcp_session_id = response_headers.get("mcp-session-id", "")
    if mcp_session_id:
        headers["mcp-session-id"] = mcp_session_id
    # initialized 是通知：部分实现回 202/空体，部分回 200；失败不改变后续调用是否合法，
    # 真正的握手错误会在下面的 tools/call 上暴露出来。
    try:
        _mcp_post({"jsonrpc": "2.0", "method": "notifications/initialized"}, headers, timeout=30.0)
    except E2eError:
        pass
    _, _, raw = _mcp_post(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
        headers,
        timeout=timeout,
    )
    result = _parse_jsonrpc(raw).get("result")
    if not isinstance(result, dict):
        raise E2eError(f"tools/call 没有 result 对象：{raw[:400]}")
    return result


def mcp_result_text(result: dict[str, Any]) -> str:
    """把 MCP 工具结果的文本块拼起来（拒绝路径只有这个，没有结构化载荷）。"""
    parts: list[str] = []
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
    return "\n".join(parts)


def mcp_result_payload(result: dict[str, Any]) -> dict[str, Any]:
    """取工具返回的 JSON 载荷：优先 ``structuredContent``，否则解析文本块里的 JSON。"""
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    text = mcp_result_text(result).strip()
    if not text.startswith("{"):
        return {}
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
