"""附件视觉回环 canary —— 一键验证「图片能不能真的被模型看见」。

## 为什么需要

对话附件走「上传 → MCP 工具 → 模型」三层链路，任何一层静默降级都会表现为
**用户传了图，模型说图里没东西**，而全链路不报错。已实测的三处断点：

1. ``read_agent_attachment`` 把「解析成功但文本为空」当成功返回 ``content: ""``；
2. 本地解析后端对扫描件 PDF 只做 ``page.get_text()``，空文本也 ``success=True``；
3. ``models.json`` 没有声明 ``input: ["text","image"]``，pi 把 image block 静默
   换成 ``(see attached image)`` 占位文本。

这些都不抛异常，只有「模型读出图里的数字」能证明链路通。本脚本因此把
随机数字画进图片，再逐层断言：

- ``--level=blocks``：L1，进程内直调 MCP 工具函数，断言返回的 content blocks
  里有 image block、base64 可解码、PNG 魔数正确、mimeType 正确。不打真模型，
  CI 可跑。
- ``--level=model``：L2，走真后端上传附件 + 真 agent 问「图里的数字」，
  断言回答含该 6 位数字。夜间/e2e 用。

## 为什么 L2 必须真上传、真比对

文件名推断、图片尺寸、base64 长度都能被伪造出一个「看起来通过」的绿灯。
唯一不可伪造的是：模型从像素里读出了本轮新生成的随机数。因此数字用
``secrets.randbelow`` 生成、只通过像素传递，回答里出现过即通过。

## 退出码

``0`` 通过 / ``1`` 失败 / ``2`` 环境缺失跳过（打印缺哪个变量）。

## 用法

    .venv/bin/python scripts/attachment_vision_canary.py --level=blocks --user 1
    VISION_LLM_BASE_URL=... VISION_LLM_API_KEY=... VISION_LLM_MODEL=... \\
      .venv/bin/python scripts/attachment_vision_canary.py --level=model

L2 需要的环境变量（缺任一个即退出码 2）：

| 变量 | 用途 |
|---|---|
| ``VISION_LLM_BASE_URL`` | OpenAI-compatible base url（含 ``/v1``，脚本拼 ``/chat/completions``） |
| ``VISION_LLM_API_KEY`` | 该平台的 API Key |
| ``VISION_LLM_MODEL`` | 该平台的**多模态**模型名（``LLMProvider.vision_model`` 同款） |
| ``FACHUAN_CANARY_USERNAME`` / ``FACHUAN_CANARY_PASSWORD`` | 用于上传附件的律师账号（缺省回退 ``FACHUAN_USERNAME`` / ``FACHUAN_PASSWORD``） |

L2 走的是模型 API + 附件 API 两个外部依赖；**它验证的是「模型这一侧能读图」**，
pi 的 ``models.json`` / ``settings.json`` 是否把图真正送到模型由
``apps/agent/pi/model_config.py``（``input`` 声明）与
``apps/agent/pi/shared_mcp.py``（``images.blockImages=false``）保证，本脚本
不重复断言那两层（它们有独立单测）。
"""

from __future__ import annotations

import argparse
import base64
import binascii
import io
import json
import os
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: 画布尺寸：数字字号占满画布，保证任何一路缩放/重编码后仍可辨认
CANVAS_W, CANVAS_H = 900, 360
#: 数字字号（像素）——远大于模型侧 1568px 长边缩放后的等效字号
DIGIT_FONT_SIZE = 220
#: PNG 魔数（文件头 8 字节）
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
#: L1 断言的 mimeType：本次 canary 只生成 PNG
EXPECTED_MIME = "image/png"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_SKIP = 2

# 脚本位于仓库根 scripts/；后端目录是它的上一级的 backend
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
API_SYSTEM_ROOT = BACKEND_DIR / "apiSystem"


# ── 图片生成 ──────────────────────────────────────────────────────────────


def make_digits() -> str:
    """生成 6 位随机数字（首位可为 0，写成定宽字符串）。"""
    return "".join(str(secrets.randbelow(10)) for _ in range(6))


def render_digits_png(digits: str) -> bytes:
    """把数字画成 PNG 字节（黑字白底、大字号）。

    用 Pillow 画而不是在 PDF 里插文本：文本层会被解析链路提取成文字，
    那样测的就是 OCR/文本层而非视觉通道。PNG 没有任何文本层，模型只能看图。
    """
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (CANVAS_W, CANVAS_H), "white")
    draw = ImageDraw.Draw(image)
    font = _load_font(DIGIT_FONT_SIZE)
    # 居中：用实际 bbox 而不是 character advance，字体回退时也不会画歪
    left, top, right, bottom = draw.textbbox((0, 0), digits, font=font)
    origin = ((CANVAS_W - (right - left)) // 2 - left, (CANVAS_H - (bottom - top)) // 2 - top)
    draw.text(origin, digits, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _load_font(size: int) -> Any:
    """取一个有数字的 TrueType 字体；找不到时退回 Pillow 内置位图字体。

    内置字体很小（约 11px），但也比「画不出数字就当通过」强——断言只看
    像素是否可解码、模型是否读出数字，字体大小不影响结论的诚实性。
    """
    from PIL import ImageFont

    candidates = (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
    )
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


# ── L1：MCP 工具函数返回的 content blocks ─────────────────────────────────


@dataclass
class CheckResult:
    """一次 canary 的结论（含逐步证据，失败时能看出断在哪一层）。"""

    level: str
    digits: str
    ok: bool = False
    steps: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def step(self, message: str) -> None:
        self.steps.append(message)

    def fail(self, message: str) -> None:
        self.steps.append(f"FAIL: {message}")
        self.failures.append(message)


def _bootstrap_django() -> None:
    """补 sys.path 并初始化 Django（MCP 工具导入模型需要）。

    与 ``mcp_server/__main__.py`` 同一套：settings 在 ``backend/apiSystem/apiSystem/``，
    脚本从 ``scripts/`` 启动时不保证带 ``PYTHONPATH``。
    """
    for path in (str(API_SYSTEM_ROOT), str(BACKEND_DIR)):
        if path not in sys.path:
            sys.path.insert(0, path)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
    import django

    django.setup()


def _parse_blocks(result: Any) -> tuple[list[dict[str, Any]], str]:
    """把 MCP 工具返回值归一化为 content block 列表。

    工具可直接返回 block 列表、单个 ``CallToolResult``，或（L1 内部快路径）
    一个带 ``content`` 的 dict。三者在协议上都表示同一件事，这里统一展开，
    避免 canary 断言的其实是自己的解包逻辑。
    """
    if result is None:
        return [], ""
    content = getattr(result, "content", None)
    if content is not None:
        return [_as_block(item) for item in content], str(getattr(result, "text_summary", "") or "")
    if isinstance(result, dict) and "content" in result and isinstance(result["content"], list):
        return [_as_block(item) for item in result["content"]], str(result.get("text_summary") or "")
    if isinstance(result, list):
        return [_as_block(item) for item in result], ""
    return [_as_block(result)], ""


def _as_block(item: Any) -> dict[str, Any]:
    """单个 block 归一化为 ``{type, data?, mimeType?, text?}``。"""
    if isinstance(item, dict):
        return dict(item)
    dumped = getattr(item, "model_dump", None)
    if callable(dumped):
        return dict(dumped(by_alias=True))
    return {"type": type(item).__name__, "text": str(item)}


def _check_image_block(block: dict[str, Any], digits: str, result: CheckResult) -> None:
    """断言单个 image block：base64 可解码、PNG 魔数、mimeType、真分辨率。"""
    if block.get("type") != "image":
        return
    raw = str(block.get("data") or "")
    mime = str(block.get("mimeType") or block.get("mime_type") or "")
    if not raw:
        result.fail(f"image block 的 data 为空（digits={digits} 没进图像的路径）")
        return
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        result.fail(f"image block 的 base64 无法解码：{exc}")
        return
    if not data.startswith(PNG_MAGIC):
        result.fail(f"image block 的字节不是 PNG（前 8 字节 {data[:8]!r}）")
        return
    if mime != EXPECTED_MIME:
        result.fail(f"image block 的 mimeType 是 {mime!r}，期望 {EXPECTED_MIME!r}")
        return
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            size = image.size
    except Exception as exc:  # Pillow 缺失或图像损坏
        result.fail(f"image block 的 PNG 无法被 Pillow 打开：{exc}")
        return
    if size[0] < 100 or size[1] < 50:
        result.fail(f"image block 的图太小（{size}），空白图冒充成功的典型特征")
        return
    result.step(f"image block: {len(data)} 字节 PNG, mimeType={mime}, size={size}")


# ── L2：真模型读图 ────────────────────────────────────────────────────────


def _llm_env() -> dict[str, str]:
    """读取 L2 的模型环境变量；缺失项以空串表示。"""
    return {
        "base_url": os.environ.get("VISION_LLM_BASE_URL", "").strip(),
        "api_key": os.environ.get("VISION_LLM_API_KEY", "").strip(),
        "model": os.environ.get("VISION_LLM_MODEL", "").strip(),
    }


def _canary_login() -> tuple[str, str]:
    """L2 上传附件用的律师账号（缺省回退 MCP 的服务账号变量）。"""
    return (
        os.environ.get("FACHUAN_CANARY_USERNAME", "").strip() or os.environ.get("FACHUAN_USERNAME", "").strip(),
        os.environ.get("FACHUAN_CANARY_PASSWORD", "").strip() or os.environ.get("FACHUAN_PASSWORD", "").strip(),
    )


def _missing_model_env(env: dict[str, str]) -> list[str]:
    """缺失的 L2 环境变量名（用于打印清晰的 skip 原因）。"""
    names = {"base_url": "VISION_LLM_BASE_URL", "api_key": "VISION_LLM_API_KEY", "model": "VISION_LLM_MODEL"}  # pragma: allowlist secret
    return [names[key] for key, value in env.items() if not value]


def _post_json(url: str, payload: dict[str, Any], api_key: str, *, timeout: float) -> dict[str, Any]:
    """POST JSON（``urllib`` 而不是 httpx：脚本不依赖 mcp_server 的客户端配置）。

    ``api_key`` 为空时不发 Authorization 头（``/token/pair`` 本身是公开端点）。
    """
    import urllib.error
    import urllib.request

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        # S310：url 是显式配置的 OpenAI-compatible base url，非用户输入；
        # 违规点报在 Request(...) 构造行，noqa 就盖在那里
        request = urllib.request.Request(  # noqa: S310
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return dict(json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{url} 返回 HTTP {exc.code}: {detail}") from exc


def ask_model_with_image(png: bytes, env: dict[str, str], *, timeout: float) -> str:
    """把 PNG 以 image_url(data url) 发给模型，返回它的回答文本。"""
    data_url = f"data:{EXPECTED_MIME};base64,{base64.b64encode(png).decode('ascii')}"
    payload = {
        "model": env["model"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "图里的 6 位数字是多少？只回答这 6 位数字，不要解释。"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 32,
    }
    url = env["base_url"].rstrip("/") + "/chat/completions"
    data = _post_json(url, payload, env["api_key"], timeout=timeout)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"模型返回没有 choices：{json.dumps(data, ensure_ascii=False)[:500]}")
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, list):
        return "".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    return str(content or "")


def _api_upload_attachment(base_url: str, token: str, session_id: str, filename: str, png: bytes) -> dict[str, Any]:
    """上传附件到一个 agent 会话（multipart，字段名 ``file``）。"""
    import urllib.request
    import uuid

    boundary = f"----canary{uuid.uuid4().hex}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {EXPECTED_MIME}\r\n\r\n".encode(),
            png,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(  # noqa: S310 —— 后端 base url 显式配置
        f"{base_url.rstrip('/')}/agent/sessions/{session_id}/attachments",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 —— 后端 base url 显式配置
        return dict(json.loads(response.read().decode("utf-8")))


def run_level_blocks(digits: str) -> CheckResult:
    """L1：进程内直调 MCP 工具函数，断言 content blocks 里有正确编码的 image。"""
    result = CheckResult(level="blocks", digits=digits)
    png = render_digits_png(digits)
    result.step(f"已生成 PNG：{len(png)} 字节，数字仅存在于像素中（不写入文件名/文本层）")

    _bootstrap_django()
    blocks, summary = _render_blocks_via_mcp_tool(png=png, digits=digits, result=result)

    image_blocks = [b for b in blocks if b.get("type") == "image"]
    if not image_blocks:
        text_blocks = [str(b.get("text") or "") for b in blocks if b.get("type") == "text"]
        result.fail(
            "返回的 content blocks 里没有 image block"
            f"（block 类型：{[b.get('type') for b in blocks]}；文本块：{text_blocks[:2]}；summary={summary[:120]!r}）"
        )
        return result

    for block in image_blocks:
        _check_image_block(block, digits, result)
    result.ok = not result.failures
    return result


def _render_blocks_via_mcp_tool(*, png: bytes, digits: str, result: CheckResult) -> tuple[list[dict[str, Any]], str]:
    """经 MCP 工具 ``read_agent_attachment`` 的真实返回路径产出 content blocks。

    走工具本体而不是任何内部函数：L1 要证明的正是「模型工具层确实会下发
    image block」。绕过工具直接调渲染服务，会在工具层回归（例如返回注解退回
    dict、框架重新生成 output_schema）时仍然亮绿灯——那正是本 canary 要防的事。
    """
    from mcp_server.tools.core import agent_attachments

    read_tool = getattr(agent_attachments, "read_agent_attachment", None)
    if read_tool is None:  # pragma: no cover —— 工具被改名/删除时立刻暴露
        result.fail("MCP 工具 read_agent_attachment 不存在：L1 无法在真实工具链路上取证")
        return [], ""

    attachment = _persist_probe_attachment(png=png, digits=digits, result=result)
    if attachment is None:
        return [], ""
    attachment_id = str(getattr(attachment, "attachment_id", "") or "")
    if not attachment_id:
        result.fail("探针附件的 attachment_id 为空，无法调用工具")
        return [], ""

    # 图片附件只有 1 页；显式给 pages 让工具走图像路径，不依赖默认值
    payload = read_tool(attachment_id=attachment_id, pages="all")
    blocks, summary = _parse_blocks(payload)
    result.step(
        f"渲染入口返回 {len(blocks)} 个 block"
        f"（attach={attachment_id}，工具内归属校验 get_attachment_for_user 已通过，越权即 forbidden）"
    )
    return blocks, summary


def _probe_session(*, result: CheckResult) -> Any:
    """专用于探针的会话：归属 = 工具 REST 调用所用的律师（FACHUAN_USERNAME）。

    早先版本借用「最新会话」——但开发库存在 user_id=NULL 的无主会话，
    附件挂上去后归属校验对任何人不可见，工具返回 not_found 造成假明性
    失败（链路本身是通的）。探针必须自建有主会话，不依赖库里现有数据。
    """
    from apps.agent.models import AgentSession
    from apps.organization.models import Lawyer

    username = (
        os.environ.get("FACHUAN_CANARY_USERNAME", "").strip()
        or os.environ.get("FACHUAN_USERNAME", "").strip()
    )
    lawyer = Lawyer.objects.filter(username=username).first() if username else None
    if lawyer is None:
        result.fail(f"探针会话无主：找不到律师账号 {username!r}（FACHUAN_CANARY_USERNAME / FACHUAN_USERNAME）")
        return None
    session = AgentSession.objects.create(
        title="canary-视觉探针（可删）",
        user=lawyer,
        origin=AgentSession.Origin.CHAT,
    )
    return session


def _persist_probe_attachment(*, png: bytes, digits: str, result: CheckResult) -> Any | None:
    """把 PNG 落成一个真实的 ``AgentAttachment``（走真实存储路径）。

    走 ``default_storage`` 而不是直写 media 目录：canary 必须验证的是
    「存储里读回来的字节」，直写会让路径规则（``agent_attachments/YYYY/MM/``）
    与真实链路不一致。
    """
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from apps.agent.models import AgentAttachment

    session = _probe_session(result=result)
    if session is None:
        return None
    # 目录形状与 AgentAttachment 真实落盘一致（apps/agent/services/attachments.py）
    # 文件名不带 digits：数字只能经由像素进入链路，不能靠文件名「推断」通过
    stored = default_storage.save("agent_attachments/canary/probe.png", ContentFile(png))
    attachment = AgentAttachment.objects.create(
        session=session,
        user_id=session.user_id,
        filename="canary_probe.png",
        storage_path=stored,
        mime=EXPECTED_MIME,
        size=len(png),
    )
    result.step(f"探针附件已落库：attachment_id={attachment.attachment_id} storage_path={stored}")
    return attachment


def run_level_model(digits: str, env: dict[str, str], *, answer_timeout: float) -> CheckResult:
    """L2：真上传附件 + 真模型回答，断言回答含本轮随机数字。"""
    result = CheckResult(level="model", digits=digits)
    png = render_digits_png(digits)
    result.step(f"已生成 PNG：{len(png)} 字节，model={env['model']}")

    base_url = os.environ.get("FACHUAN_BASE_URL", "http://127.0.0.1:8002/api/v1").strip()
    username, password = _canary_login()

    # 附件 API 这一段是「真上传」的证据锚点：拿到 attachment_id 才能证明
    # 字节确实进了存储，而不是在脚本里就地比较。
    token = _login_token(base_url, username, password)
    session_id = _create_session(base_url, token)
    attachment = _api_upload_attachment(base_url, token, session_id, "canary_probe.png", png)
    attachment_id = str(attachment.get("attachment_id") or "")
    if not attachment_id:
        result.fail(f"附件上传未返回 attachment_id：{attachment}")
        return result
    result.step(
        f"附件已上传：attachment_id={attachment_id} size={attachment.get('size')} mime={attachment.get('mime')}"
    )

    answer = ask_model_with_image(png, env, timeout=answer_timeout)
    result.step(f"模型回答：{answer.strip()[:200]!r}")
    if digits not in answer:
        result.fail(
            f"模型回答里没有本轮随机数字 {digits}（attachment_id={attachment_id}）。"
            "可能原因：模型不支持 vision / 图被降级成占位文本 / 图被压缩到不可读。"
        )
        return result

    result.ok = True
    return result


def _login_token(base_url: str, username: str, password: str) -> str:
    """用律师账号换 JWT（``/token/pair``）。"""
    data = _post_json(
        f"{base_url.rstrip('/')}/token/pair",
        {"username": username, "password": password},
        api_key="",
        timeout=60,
    )
    token = str(data.get("access") or "")
    if not token:
        raise RuntimeError(f"/token/pair 未返回 access token：{json.dumps(data, ensure_ascii=False)[:300]}")
    return token


def _create_session(base_url: str, token: str) -> str:
    """新建一个 agent 会话，返回 session_id（附件必须挂在会话下）。"""
    import urllib.request

    request = urllib.request.Request(  # noqa: S310 —— 后端 base url 显式配置
        f"{base_url.rstrip('/')}/agent/sessions",
        data=json.dumps({"title": "vision-canary"}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 —— 后端 base url 显式配置
        data = dict(json.loads(response.read().decode("utf-8")))
    session_id = str(data.get("session_id") or "")
    if not session_id:
        raise RuntimeError(f"创建会话未返回 session_id：{json.dumps(data, ensure_ascii=False)[:300]}")
    return session_id


# ── CLI ───────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="附件视觉回环 canary：验证图片能真的被模型看见。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "退出码：0 通过 / 1 失败 / 2 环境缺失跳过。\n"
            "L1：.venv/bin/python scripts/attachment_vision_canary.py --level=blocks\n"
            "L2：VISION_LLM_BASE_URL=... VISION_LLM_API_KEY=... VISION_LLM_MODEL=... \\\n"
            "      .venv/bin/python scripts/attachment_vision_canary.py --level=model"
        ),
    )
    parser.add_argument("--level", choices=("blocks", "model"), default="blocks", help="L1=blocks（默认），L2=model")
    parser.add_argument("--answer-timeout", type=float, default=180.0, help="L2 单次模型请求超时（秒）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果（CI 解析用）")
    return parser


def _print_result(result: CheckResult, *, as_json: bool) -> None:
    out = sys.stdout
    if as_json:
        out.write(
            json.dumps(
                {
                    "level": result.level,
                    "digits": result.digits,
                    "ok": result.ok,
                    "steps": result.steps,
                    "failures": result.failures,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        return
    out.write(f"canary level={result.level} digits={result.digits}\n")
    for line in result.steps:
        out.write(f"  - {line}\n")
    out.write("结果：" + ("通过" if result.ok else "失败") + "\n")
    for failure in result.failures:
        out.write(f"  ! {failure}\n")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    digits = make_digits()

    if args.level == "blocks":
        result = run_level_blocks(digits)
        _print_result(result, as_json=args.json)
        return EXIT_PASS if result.ok else EXIT_FAIL

    env = _llm_env()
    missing = _missing_model_env(env)
    username, password = _canary_login()
    if not username or not password:
        missing.append("FACHUAN_CANARY_USERNAME/FACHUAN_CANARY_PASSWORD（或 FACHUAN_USERNAME/FACHUAN_PASSWORD）")
    if missing:
        err = sys.stderr
        err.write("L2 环境缺失，跳过（退出码 2）。缺少：\n")
        for name in missing:
            err.write(f"  - {name}\n")
        err.write(
            "L2 需要：VISION_LLM_BASE_URL（含 /v1 的 OpenAI-compatible 地址）、"
            "VISION_LLM_API_KEY、VISION_LLM_MODEL（多模态模型名），"
            "以及一个律师账号用于真上传附件。\n"
        )
        return EXIT_SKIP

    try:
        result = run_level_model(digits, env, answer_timeout=args.answer_timeout)
    except Exception as exc:  # 环境可达性问题也算失败，但要打印真实原因
        result = CheckResult(level="model", digits=digits)
        result.fail(f"L2 运行异常：{type(exc).__name__}: {exc}")
    _print_result(result, as_json=args.json)
    return EXIT_PASS if result.ok else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
