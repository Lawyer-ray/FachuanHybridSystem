#!/usr/bin/env python3
"""真机场景矩阵里**只能在真 DS 上验**的那几条。

后端可确定性验证的场景见
`backend/tests/ci/unit/doc_workspace/test_scenario_matrix.py`；两者的对应关系与
「为什么有些场景不在这里」记在
`docs/analysis/onlyoffice-ai-2026-11-26/scenario-matrix.md`。

跑法（DS 需在跑）：

```bash
cd backend
DB_NAME=fachuan_dev .venv/bin/python ../deploy/onlyoffice/harness/scenario_matrix.py --out /tmp/oo-matrix.docx
```
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import plugin_e2e as base  # noqa: E402  （同目录 harness，非包）


def _driver_two_editors() -> str:
    """两个浏览器页同开同一份文档：A 加批注，B 触发保存。

    验的是 DS 的协同收敛：**同一 document key** 下，A 的编辑必须出现在 B 触发的
    保存里。如果 key 算错（比如把签名参数混进哈希），两个页会变成两份独立文档，
    A 的批注在保存产物里就会消失——这是最容易被忽略的一种「用户以为协同了」。
    """
    return """
import { createRequire } from 'node:module'
const require = createRequire(process.env.PW_ROOT + '/')
const { chromium } = require('playwright-core')

const port = process.argv[2]
const orig = process.argv[3]
const text = process.argv[4]
const url = `http://127.0.0.1:${port}/harness.html`

const browser = await chromium.launch(
  process.env.PW_EXECUTABLE ? { executablePath: process.env.PW_EXECUTABLE } : {},
)
const out = { steps: [] }

async function openEditor() {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } })
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 })
  await page.waitForFunction(
    () => window.__events.some((e) => e.type === 'ready' || e.type === 'hello'),
    null,
    { timeout: 30000 },
  )
  return page
}

const pageA = await openEditor()
const pageB = await openEditor()
out.steps.push('two-editors-ready')

// A 加批注（协同会话应把这条同步给 B 的内核）
await pageA.evaluate(
  ([o, t]) => window.fachuan('add-comments', { comments: [{ orig: o, text: t }] }),
  [orig, text],
)
await pageA.waitForFunction(() => window.__events.some((e) => e.type === 'commented'), null, { timeout: 40000 })
out.commentedOnA = await pageA.evaluate(
  () => window.__events.filter((e) => e.type === 'commented').pop().data.result,
)

// 等协同把 A 的编辑推给 B
await pageB.waitForTimeout(3000)

// B 触发保存：落盘的必须是**协同会话**的内容（含 A 的批注）
await pageB.evaluate(() => window.__editor.serviceCommand({ c: 'forcesave' }))
await pageB.waitForTimeout(4000)

console.log(JSON.stringify(out))
await browser.close()
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/oo-matrix.docx")
    ap.add_argument("--port", type=int, default=18766)
    args = ap.parse_args()

    base._bootstrap_django()
    from apps.onlyoffice.config import get_config

    cfg = get_config()
    if not cfg.enabled:
        print("OnlyOffice 未配置，无法真机验证", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.unlink(missing_ok=True)

    config = base._signed_config(
        host="host.docker.internal",
        port=args.port,
        file_name="matrix.docx",
        jwt_secret=cfg.jwt_secret,
        docserver=cfg.docserver_url,
    )
    handler = type(
        "_H",
        (base._Handler,),
        {
            "docx_bytes": base._test_docx(),
            "config": config,
            "out_path": out_path,
            "docserver": cfg.docserver_url,
        },
    )
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"harness 就绪: http://127.0.0.1:{args.port}/harness.html")

    failures: list[str] = []
    try:
        pw_root = base._playwright_root()
        if pw_root is None:
            raise RuntimeError("找不到 playwright-core")
        driver = Path(__file__).with_name("_driver_matrix.mjs")
        driver.write_text(_driver_two_editors())
        try:
            proc = subprocess.run(
                ["node", str(driver), str(args.port), base.TEST_PARAGRAPH, base.COMMENT_TEXT],
                capture_output=True,
                text=True,
                timeout=300,
                env={**__import__("os").environ, "PW_ROOT": pw_root, "PW_EXECUTABLE": base._chromium_executable() or ""},
            )
        finally:
            driver.unlink(missing_ok=True)
        if proc.returncode != 0:
            raise RuntimeError(f"驱动失败:\n{proc.stderr[-3000:]}")

        result: dict[str, Any] = {}
        for line in reversed(proc.stdout.strip().splitlines()):
            if line.strip().startswith("{"):
                result = json.loads(line)
                break
        commented = result.get("commentedOnA") or {}
        print("A 页批注回执:", json.dumps(commented, ensure_ascii=False))
        if not commented.get("ok"):
            failures.append(f"A 页加批注失败: {commented}")

        for _ in range(60):
            if out_path.exists() and out_path.stat().st_size > 0:
                break
            time.sleep(1)
        if not out_path.exists():
            failures.append("B 页触发的保存没有落盘")
            raise SystemExit(_report(failures))

        import zipfile

        with zipfile.ZipFile(out_path) as zf:
            names = zf.namelist()
            xml = zf.read("word/comments.xml").decode("utf-8") if "word/comments.xml" in names else ""
        if "法穿AI" not in xml:
            failures.append("B 页触发的保存里没有 A 页加的批注（协同没收敛 / document key 不一致）")
        if base.COMMENT_TEXT not in xml:
            failures.append("落盘批注正文与 A 页输入不一致")
    finally:
        server.shutdown()

    return _report(failures)


def _report(failures: list[str]) -> int:
    if failures:
        print("\n❌ 失败项:")
        for f in failures:
            print(" -", f)
        return 1
    print("\n✅ 两页同开场景通过：A 页的批注出现在 B 页触发的保存产物里")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
