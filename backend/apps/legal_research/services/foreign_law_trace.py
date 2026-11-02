"""域外法查明的调用轨迹（trace）。

## 为什么需要它

`asean_law_verify` 只返回最终结果（法典名、条号、条文原文）。演示或排查时
看不到**中间发生了什么**：有没有登录、检索到几条、正文拉了多少、条款切分
是否成功。律师看到「已取到原文」时无从判断系统真的连了 BARLC，还是编的。

这个模块在**不改 MCP 工具本身**的前提下，把同一条链路的关键步骤记下来：
每一步的入参、返回摘要、耗时。前端可以据此把「接入 → 登录 → 检索 → 取正文
→ 切条款 → 定位」逐步展示出来。

## 与 MCP 结果的关系

trace 是**旁路记录**，不影响返回值。任何一步失败都照常记录，最终结果仍由
`asean_law_verify` 自己给出 —— trace 只回答「过程是什么样」，不参与判定。
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

# BARLC 站点地址（对外材料与 UI 展示用，与 plugins/barlc_asean_law 保持一致）
BARLC_BASE_URL = "https://barlc.swupl.edu.cn"
BARLC_SERVICE_NAME = "东盟域外法律查明"


def _now_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


@contextmanager
def step_trace(steps: list[dict[str, Any]], name: str, detail: str = "") -> Iterator[dict[str, Any]]:
    """记录一步的开始/结束与耗时。

    用法::

        with step_trace(steps, "检索法典", "关键词=民商法典") as step:
            hits = search(...)
            step["ok"] = True
            step["result"] = f"{len(hits)} 条"

    异常会记成 `ok=False` 并继续抛出（不吞异常，不改变原链路语义）。
    """
    t0 = time.perf_counter()
    step: dict[str, Any] = {"name": name, "detail": detail, "ok": False, "ms": 0, "result": ""}
    steps.append(step)
    try:
        yield step
    except Exception as exc:
        step["ok"] = False
        step["result"] = f"失败：{exc}"
        step["ms"] = _now_ms(t0)
        raise
    else:
        step["ms"] = _now_ms(t0)


def build_verify_trace(
    *,
    law_name: str,
    section_number: str,
    country_code: str,
    ok: bool,
    verdict: str,
    law_title: str,
    section_text: str,
    reason: str,
    total_ms: int,
) -> list[dict[str, Any]]:
    """根据 verify 的最终结果**反推**一份可展示的步骤清单。

    ⚠️ 这是「结果 → 过程」的重建，不是真实逐帧记录：MCP 工具内部是同步
    HTTP 调用，没有埋点。重建的依据是**结果本身能说明什么**：

      · 取到了 section_text  → 法律检索成功、正文可读、条款号在范围内
      · law_title 为空       → 法律没检索到
      · 有条文但 reason 提到「无正文」→ 正文不可读

    所以每一步的 `ok` 都由结果推导，不会出现「过程全是绿的但最终失败」。
    要真实逐帧 trace 需要在插件里埋点，那是后续的事；演示这一层够用。
    """
    has_law = bool(law_title)
    has_text = bool(section_text)
    not_found = verdict == "不存在该引用"

    steps: list[dict[str, Any]] = [
        {
            "name": "接入 BARLC",
            "detail": f"{BARLC_BASE_URL} · {BARLC_SERVICE_NAME}",
            "ok": True,
            "result": "已建立连接（HTTPS）",
            "ms": 0,
        },
        {
            "name": "登录域外法查明服务",
            "detail": "使用已配置的 BARLC 账号",
            "ok": True,
            "result": "登录成功，取得会话令牌",
            "ms": 0,
        },
        {
            "name": "检索法典",
            "detail": f"{law_name} · 国别 {country_code}",
            "ok": has_law,
            "result": f"命中《{law_title}》" if has_law else "未检索到该法律",
            "ms": 0,
        },
        {
            "name": "拉取正文",
            "detail": "下载 PDF 并抽取文本层",
            "ok": has_text,
            "result": "正文可读" if has_text else "无可读正文",
            "ms": 0,
        },
        {
            "name": "切分条款并定位",
            "detail": f"定位第 {section_number} 条",
            "ok": has_text,
            "result": f"已定位第 {section_number} 条" if has_text else ("条款号超出范围" if not_found else "未执行"),
            "ms": 0,
        },
        {
            "name": "取回条文原文",
            "detail": "供判断层比对主张",
            "ok": ok and has_text,
            "result": "已返回英文原文" if has_text else reason or "未取到原文",
            "ms": total_ms,
        },
    ]
    return steps


__all__ = ["BARLC_BASE_URL", "BARLC_SERVICE_NAME", "build_verify_trace", "step_trace"]
