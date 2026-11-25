#!/usr/bin/env python3
"""法穿 AI 插件桥的真机端到端验证（不需要起整个 Django + 前端）。

## 为什么要这个 harness

插件桥（`deploy/onlyoffice/plugins/fachuan-rewrite/`）的能力**只能在真 DS 上验**：
`AddComment` / `SetAssistantTrackRevisions` 这些内核 API 是否存在、批注落到
docx 的 `comments.xml` 长什么样，mock 一律验不出来。

但拉起整个应用（前端 dev server + 登录 + 建合同 + 绑文件夹 + 放文件）只为了
验一条批注，成本高且脆。所以这里最小化到三件事：

1. 本地起一个 HTTP 服务：提供测试 docx、harness 页面、以及一个**假的 DS 回调**
   （收到 status=2/6 → 下载 DS 给的 `url` → 落盘到 `--out`）；
2. 用后端同一把 JWT 密钥给编辑器配置签名（DS 开了 inbound JWT 就必须签）；
3. 用 playwright 打开 harness 页面 → 等插件握手 → 发 `add-comments` →
   触发 `forcesave` → 断言落盘 docx 里的 `comments.xml`。

## 用法

```bash
cd backend
DB_NAME=fachuan_dev .venv/bin/python ../deploy/onlyoffice/harness/plugin_e2e.py --out /tmp/oo-e2e.docx
```

前置：DS 容器在跑（`curl 127.0.0.1:9980/healthcheck` 为 true）。
退出码 0 = 全部断言通过。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSettings.settings")

TEST_PARAGRAPH = "甲方愿意支付人民币壹万元整。"
COMMENT_TEXT = "违约金没有上限，是否接受取决于谈判地位，请确认商务口径。"
REVISION_ORIG = "乙方应当在三十日内完成交付。"
REVISION_SUG = "乙方应当在十五日内完成交付。"
#: 画布里的登录用户（故意不叫法穿AI：用来验证 AI 修订没有挂到律师名下）
LAWYER_NAME = "张律师"


def _bootstrap_django() -> None:
    import django

    # manage.py 把 backend/apiSystem 加进 sys.path，settings 模块名是 apiSystem.settings
    sys.path.insert(0, str(BACKEND_DIR / "apiSystem"))
    os.environ["DJANGO_SETTINGS_MODULE"] = "apiSystem.settings"
    django.setup()


def _test_docx() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph(TEST_PARAGRAPH)
    doc.add_paragraph("乙方应当在三十日内完成交付。")
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _signed_config(*, host: str, port: int, file_name: str, jwt_secret: str, docserver: str) -> dict[str, Any]:
    """组一个**不经后端**的编辑器配置（签名逻辑与 signing.build_editor_config 同构）。"""
    import jwt

    config: dict[str, Any] = {
        "documentType": "word",
        "document": {
            "fileType": "docx",
            "key": f"e2e{int(time.time())}",
            "title": file_name,
            "url": f"http://{host}:{port}/test.docx",
            "permissions": {"edit": True, "review": True, "comment": True},
        },
        "editorConfig": {
            "mode": "edit",
            "lang": "zh-CN",
            "user": {"id": "e2e", "name": LAWYER_NAME},
            "callbackUrl": f"http://{host}:{port}/callback",
            "customization": {
                "autosave": True,
                "forcesave": True,
                "review": {"reviewDisplay": "markup", "showReviewChanges": True, "trackChanges": True},
            },
            # 插件本体由 DS 自己托管，autostart + pluginsData 必须成对
            "plugins": {
                "autostart": ["asc.{A67B4C8F-1F2A-4B6E-9C3D-5E8F7A2B1D04}"],
                "pluginsData": [f"{docserver.rstrip('/')}/sdkjs-plugins/fachuan-rewrite/config.json"],
            },
        },
        "type": "desktop",
        "width": "100%",
        "height": "100%",
    }
    config["token"] = jwt.encode(config, jwt_secret, algorithm="HS256")
    return config


HARNESS_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>fachuan plugin e2e</title>
<style>html,body{margin:0;height:100%}#ph{height:100%}</style>
<script src="__DOCSERVER__/web-apps/apps/api/documents/api.js"></script>
</head><body>
<div id="ph"></div>
<script>
  window.__events = [];
  window.__pluginWin = null;
  window.addEventListener('message', function (e) {
    var d = e.data;
    if (!d || d.source !== 'fachuan-plugin') return;
    if (d.type === 'ready' || d.type === 'hello') window.__pluginWin = e.source;
    window.__events.push({ at: Date.now(), type: d.type, data: d });
  });
  window.fachuan = function (action, payload) {
    if (!window.__pluginWin) return false;
    var msg = { source: 'fachuan-page', action: action };
    if (payload) msg.payload = payload;
    window.__pluginWin.postMessage(msg, '*');
    return true;
  };
  window.__ready = false;
  fetch('/config.json').then(function (r) { return r.json() }).then(function (cfg) {
    window.__editor = new DocsAPI.DocEditor('ph', Object.assign({}, cfg, {
      width: '100%', height: '100%',
      events: {
        onDocumentReady: function () { window.__ready = true; window.__events.push({ at: Date.now(), type: 'doc-ready' }); },
        onError: function (e, d) { window.__events.push({ at: Date.now(), type: 'error', data: d }); }
      }
    }));
  });
</script>
</body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    docx_bytes = b""
    config: dict[str, Any] = {}
    out_path: Path | None = None
    received: list[dict[str, Any]] = []
    host = "127.0.0.1"

    def log_message(self, *args: Any) -> None:  # 静音
        return

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/test.docx"):
            self._send(200, self.docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        elif self.path.startswith("/config.json"):
            self._send(200, json.dumps(self.config).encode(), "application/json")
        elif self.path.startswith("/harness.html") or self.path == "/":
            self._send(200, HARNESS_HTML.replace("__DOCSERVER__", self.docserver).encode(), "text/html")
        else:
            self._send(404, b"", "text/plain")

    def _read_body(self) -> bytes:
        """读请求体。

        **DS 可能用 chunked 编码回调**（没有 Content-Length）。只按
        Content-Length 读会拿到空 body，症状是「回调明明来了，但 status 恒为 0、
        文件永远不落盘」——这个 harness 第一次跑就栽在这里。
        """
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            chunks: list[bytes] = []
            while True:
                line = self.rfile.readline().strip()
                if not line:
                    break
                try:
                    size = int(line.split(b";")[0], 16)
                except ValueError:
                    break
                if size == 0:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
            return b"".join(chunks)
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def do_POST(self) -> None:  # noqa: N802
        raw = self._read_body()
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            body = {}
        self.received.append({"path": self.path, "body": body})
        inner_status = (body.get("payload") or body).get("status")
        print(f"[callback] {self.path} status={inner_status} bytes={len(raw)}", flush=True)
        inner = body.get("payload", body) if isinstance(body, dict) else {}
        status = int((inner or {}).get("status", 0) or 0)
        if status in (2, 6):
            url = str((inner or {}).get("url") or "")
            if url and self.out_path is not None:
                import httpx

                # DS 在容器里给的 url 可能是 127.0.0.1，宿主能直连
                resp = httpx.get(url, timeout=60, trust_env=False, follow_redirects=True)
                resp.raise_for_status()
                self.out_path.write_bytes(resp.content)
                print(f"[callback] saved {len(resp.content)} bytes -> {self.out_path}", flush=True)
        self._send(200, b'{"error":0}', "application/json")


def _playwright_root() -> str | None:
    """全局 node_modules 里能找到 playwright-core 的那个目录。"""
    try:
        npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return None
    for candidate in (
        Path(npm_root) / "@playwright" / "cli" / "node_modules",
        Path(npm_root),
        Path(npm_root) / "playwright" / "node_modules",
    ):
        if (candidate / "playwright-core" / "package.json").exists():
            return str(candidate)
    return None


def _chromium_executable() -> str | None:
    """选一个缓存里可用的 chromium 可执行文件（取版本号最大的那个）。"""
    cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    if not cache.exists():
        return None
    candidates: list[tuple[int, Path]] = []
    for entry in cache.glob("chromium-*"):
        try:
            rev = int(entry.name.split("-")[-1])
        except ValueError:
            continue
        for app in (
            entry / "chrome-mac-arm64" / "Google Chrome for Testing.app" / "Contents" / "MacOS" / "Google Chrome for Testing",
            entry / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
        ):
            if app.exists():
                candidates.append((rev, app))
                break
    if not candidates:
        return None
    candidates.sort()
    return str(candidates[-1][1])


def _run_browser(port: int, *, timeout_s: int) -> dict[str, Any]:
    """用 playwright-core 打开 harness、发命令、触发保存。"""
    pw_root = _playwright_root()
    if pw_root is None:
        raise RuntimeError(
            "找不到 playwright-core。装一个即可：npm i -g @playwright/cli（或 npx playwright 装一份）"
        )
    driver = Path(__file__).with_name("_driver.mjs")
    driver.write_text(
        """
import { createRequire } from 'node:module'

// 驱动器写在仓库里（不在任何 node_modules 下），ESM 解析不到全局装的
// playwright-core，所以用 createRequire 从全局根目录手动解析。
const require = createRequire(process.env.PW_ROOT + '/')
const { chromium } = require('playwright-core')

const port = process.argv[2]
const url = `http://127.0.0.1:${port}/harness.html`
// 用缓存里真实存在的 chromium：playwright-core 的版本号与已下载的浏览器
// 构建号常常对不上（实测 1.64 要 1247，缓存里是 1255），指定 executablePath
// 比要求使用者重下 100MB 浏览器更实际。
const browser = await chromium.launch(
  process.env.PW_EXECUTABLE ? { executablePath: process.env.PW_EXECUTABLE } : {},
)
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
page.on('console', (m) => console.error('[console]', m.text()))
await page.goto(url, { waitUntil: 'domcontentloaded' })

const out = { steps: [] }
async function push(label, value) { out.steps.push({ label, value }); }

await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 })
await push('doc-ready', true)

await page.waitForFunction(
  () => window.__events.some((e) => e.type === 'ready' || e.type === 'hello'),
  null,
  { timeout: 30000 },
)
await push('plugin-handshake', true)

// 能力探测（内核里 typeof 判断，不是猜）
await page.evaluate(() => window.fachuan('capabilities', {}))
await page.waitForFunction(
  () => window.__events.some((e) => e.type === 'capabilities'),
  null,
  { timeout: 30000 },
)
out.capabilities = await page.evaluate(
  () => window.__events.filter((e) => e.type === 'capabilities').pop().data.result,
)

// 加一条批注
await page.evaluate(
  ([orig, text]) => window.fachuan('add-comments', { comments: [{ orig, text }] }),
  [process.argv[3], process.argv[4]],
)
await page.waitForFunction(
  () => window.__events.some((e) => e.type === 'commented'),
  null,
  { timeout: 40000 },
)
out.commented = await page.evaluate(
  () => window.__events.filter((e) => e.type === 'commented').pop().data.result,
)

// 读回批注（验证 AddComment 真的挂上了）
await page.evaluate(() => window.fachuan('get-comments', {}))
await page.waitForFunction(
  () => window.__events.some((e) => e.type === 'comments'),
  null,
  { timeout: 30000 },
)
out.comments = await page.evaluate(
  () => window.__events.filter((e) => e.type === 'comments').pop().data.result,
)

// 落一条修订：验证 AI 署名是否与登录用户（张律师）分离
await page.evaluate(
  ([orig, sug]) => window.fachuan('apply-revision', { orig, sug }),
  [process.argv[5], process.argv[6]],
)
await page.waitForFunction(
  () => window.__events.some((e) => e.type === 'applied'),
  null,
  { timeout: 40000 },
)
out.applied = await page.evaluate(
  () => window.__events.filter((e) => e.type === 'applied').pop().data.result,
)

// 触发 forcesave —— 后端（这里是假回调）落盘的唯一正规入口
await page.evaluate(() => window.__editor.serviceCommand({ c: 'forcesave' }))
await page.waitForTimeout(4000)

console.log(JSON.stringify(out))
await browser.close()
"""
    )
    try:
        proc = subprocess.run(
            ["node", str(driver), str(port), TEST_PARAGRAPH, COMMENT_TEXT, REVISION_ORIG, REVISION_SUG],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={**os.environ, "PW_ROOT": pw_root, "PW_EXECUTABLE": (_chromium_executable() or "")},
        )
    finally:
        driver.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"浏览器驱动失败（{proc.returncode}）:\n{proc.stderr[-4000:]}")
    # stdout 里最后一行 JSON 是结果
    for line in reversed(proc.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError(f"驱动没有输出结果:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/oo-plugin-e2e.docx")
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--timeout", type=int, default=240)
    args = ap.parse_args()

    _bootstrap_django()
    from apps.onlyoffice.config import get_config

    cfg = get_config()
    if not cfg.enabled:
        print("OnlyOffice 未配置，无法真机验证", file=sys.stderr)
        return 2

    docx = _test_docx()
    config = _signed_config(
        host="host.docker.internal",
        port=args.port,
        file_name="e2e.docx",
        jwt_secret=cfg.jwt_secret,
        docserver=cfg.docserver_url,
    )

    out_path = Path(args.out)
    out_path.unlink(missing_ok=True)

    handler = type(
        "_H",
        (_Handler,),
        {"docx_bytes": docx, "config": config, "out_path": out_path, "docserver": cfg.docserver_url},
    )
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"harness 已就绪: http://127.0.0.1:{args.port}/harness.html")

    failures: list[str] = []
    try:
        result = _run_browser(args.port, timeout_s=args.timeout)
        caps = result.get("capabilities") or {}
        commented = result.get("commented") or {}
        comments = result.get("comments") or {}
        print("能力探测:", json.dumps(caps, ensure_ascii=False))
        print("批注回执:", json.dumps(commented, ensure_ascii=False))
        print("读回批注:", json.dumps(comments, ensure_ascii=False))

        if not caps.get("ok"):
            failures.append(f"能力探测失败: {caps}")
        if not commented.get("ok"):
            failures.append(f"add-comments 未成功: {commented}")

        # 等回调落盘
        for _ in range(60):
            if out_path.exists() and out_path.stat().st_size > 0:
                break
            time.sleep(1)
        if not out_path.exists():
            failures.append("没有等到 DS 的 forcesave 回调落盘")
            raise SystemExit(_report(failures))

        with zipfile.ZipFile(out_path) as zf:
            names = zf.namelist()
            if "word/comments.xml" not in names:
                failures.append(f"落盘 docx 里没有 word/comments.xml（含 {names[:8]}…）")
                raise SystemExit(_report(failures))
            xml = zf.read("word/comments.xml").decode("utf-8")
            doc_xml = zf.read("word/document.xml").decode("utf-8")

        if "法穿AI" not in xml:
            failures.append("comments.xml 里没有 AI 作者名（法穿AI）")
        if COMMENT_TEXT not in xml:
            failures.append("comments.xml 里没有批注正文")
        if "commentRangeStart" not in doc_xml:
            failures.append("document.xml 里没有 commentRangeStart 锚点")
        if "commentReference" not in doc_xml:
            failures.append("document.xml 里没有 commentReference")

        # QuoteText **不会**回显到 comments.xml 里：DS 把它当成「在正文里找哪一段」
        # 的定位依据，落盘后只剩 document.xml 里的 commentRangeStart/End 包住的范围。
        # 所以要验证「锚点对不对」得解析那段范围里到底是什么字。
        anchored = _commented_text(doc_xml)
        print("批注锚定到的原文:", anchored)
        if TEST_PARAGRAPH not in anchored:
            failures.append(f"批注锚定的范围里没有原文（得到：{anchored!r}）")

        # AI 修订的署名必须与登录用户（张律师）分离 —— 这是客户能不能看出
        # 「哪条是 AI 建议、哪条是律师改的」的全部依据。
        authored = set(re.findall(r'w:author="([^"]+)"', doc_xml))
        print("文档里的修订作者:", sorted(authored))
        if "法穿AI" not in authored:
            failures.append(f"AI 修订没有署名为法穿AI（实际作者：{sorted(authored)}）")
        if "法穿AI" in authored and LAWYER_NAME in authored:
            print("✅ AI 修订与律师修订的作者可区分")

        # 顺带确认回落作者名：rev 场景留给 test_author_normalizer
        m = re.search(r'w:author="([^"]+)"', xml)
        if m:
            print("批注作者:", m.group(1))
    finally:
        server.shutdown()

    return _report(failures)


def _commented_text(document_xml: str) -> str:
    """取 `w:commentRangeStart` 到 `w:commentRangeEnd` 之间的可见文本。"""
    from lxml import etree

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = etree.fromstring(document_xml.encode("utf-8"))
    collected: list[str] = []
    inside = False
    for elem in root.iter():
        tag = etree.QName(elem).localname
        if tag == "commentRangeStart":
            inside = True
            continue
        if tag == "commentRangeEnd":
            inside = False
            continue
        if inside and tag == "t":
            collected.append(elem.text or "")
    del ns
    return "".join(collected)


def _report(failures: list[str]) -> int:
    if failures:
        print("\n❌ 失败项:")
        for f in failures:
            print(" -", f)
        return 1
    print("\n✅ 真机验证通过：批注经 DS 落进 comments.xml，作者与 QuoteText 都对")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
