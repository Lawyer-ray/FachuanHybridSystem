"""划词直改：律师框选一段、说一句「这么改」，AI 出候选，采纳后落成 Word 修订。

## 与合同审查（`contract_reviewer`）的关系

**不是同一套逻辑，只共用零件**。两者的差别在输入端决定了全部输出：

| | 合同审查 | 划词直改 |
|---|---|---|
| 触发 | 打开整份合同，跑全篇 | 律师框住一段，说一句话 |
| 立场 | **必须选**（甲方还是乙方），方向相反 | **不需要**——律师已经把意图说出来了 |
| 范围 | 全文逐条扫 | 只有选区 |
| 输出 | 风险清单 + 等级 + 评估报告 | 2~3 条改写候选，无等级、无报告 |
| 决策 | 逐条采纳/驳回 | 挑一条候选，其余丢弃 |

所以这里**不引入** `represented_party` / `party_a` / `party_b`：没有立场，prompt
里问「代表谁的利益」只会让模型自行脑补一个立场，把律师的指令带偏。
`client_demands` 这类客户交代也不进 prompt——本次改写的全部意图就是
`instruction` 那一句话。

## 为什么返回多条候选

一段话往往有几种改法（弱化、强化、折中）。审查流水线只给一条，是因为
律师要快速过 30 处；划词改是一对一的精细活，让律师挑比让模型猜准更划算。

## 为什么不在这里落盘

`apply()` 只接收律师已选定的那一条文本。生成候选是无副作用的纯 LLM 调用，
LLM 挂了、超时、返回垃圾都不该动到文件；只有律师点了「采纳」才写盘。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from apps.core.exceptions import ValidationException
from apps.core.llm.service import LLMService, get_llm_service

logger = logging.getLogger(__name__)

# 候选条数硬上限：律师挑的是一个「更好的说法」，给 5 条以上反而增加选择成本
MAX_CANDIDATES = 3

# 选区长度上限。条款通常几百字；给到 4000 字足以覆盖一个长条款，
# 再往上就不是「一句条款」而是「一整节的改写」——那种应当走审查流水线。
MAX_SELECTION_CHARS = 4000

# 上下文窗口：选区前后各留这么多字符。模型需要知道「这段话在什么语境里」
# （前文是定义还是列举、后文还有没有但书），否则会把独立句子改得与上下文脱节。
CONTEXT_WINDOW = 600


@dataclass(frozen=True)
class EditCandidate:
    """一条改写候选。"""

    suggested: str
    reason: str
    """为什么这么改（一句话）。不参与落盘，只给律师决策用。"""


def build_rewrite_prompt(*, selection: str, instruction: str, context_before: str, context_after: str) -> str:
    """组 prompt：无立场、只按指令改写选区。

    刻意把「选区」与「上下文」分成两个块：模型很容易把上下文里的句子
    一起改掉，导致替换时定位失败（选区原文已不连续）。分开标注 + 明确
    要求「只改选区」，是保证 `apply_revision` 能精确命中的前提。
    """
    before_block = f"## 选区之前的文字（仅供理解语境，**不要修改**）\n{context_before}\n\n" if context_before else ""
    after_block = f"## 选区之后的文字（仅供理解语境，**不要修改**）\n{context_after}\n\n" if context_after else ""
    return (
        "你是资深合同律师。律师已经框选了合同中的一段文字，并给出了修改要求。"
        "请按该要求改写**框选的这一段**。\n\n"
        f"## 律师的修改要求\n{instruction}\n\n"
        f"{before_block}"
        f"## 待修改的选区原文\n{selection}\n\n"
        f"{after_block}"
        "## 输出要求\n"
        "- 只改写「选区原文」，不要触碰上下文\n"
        "- 保留法律文书语体：书面、严谨、条文式，不要口语化\n"
        "- 保留原文的编号、标点习惯与称呼（甲方/乙方/本合同等）\n"
        "- 改写后仍是一段可直接替换的连续文本，不要输出解释、标题或 Markdown\n"
        f"- 给出 {MAX_CANDIDATES} 条**取向不同**的候选（例如：偏保守、偏强势、折中），"
        "不要给出三条几乎一样的措辞\n"
        "- 每条候选的 reason 用一句话说明改写思路（不超过 40 字）\n\n"
        "仅返回 JSON 数组，不要任何其他内容：\n"
        '[{"suggested": "改写后的完整文本", "reason": "改写思路"}]\n'
    )


def _strip_code_fence(text: str) -> str:
    """剥掉 ```json … ``` 外壳。模型常见输出，直接 json.loads 会失败。"""
    t = text.strip()
    if "```" not in t:
        return t
    start = t.find("[")
    end = t.rfind("]")
    if start >= 0 and end > start:
        return t[start : end + 1]
    return t


def parse_candidates(raw: str) -> list[EditCandidate]:
    """解析 LLM 返回的候选数组。

    容错优先：模型可能返回非 JSON、缺字段、或只给一个字符串。解析不出
    就返回空列表由调用方报错——**绝不**把模型原文当候选文本返回，那样
    律师点「采纳」就会把一段解释性文字塞进合同。
    """
    text = _strip_code_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("划词直改：LLM 返回非 JSON，长度 %d，开头：%s", len(text), text[:200])
        return []

    if isinstance(data, dict):
        # 有些模型会包一层 {"candidates": [...]}
        for key in ("candidates", "results", "edits", "suggestions"):
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if not isinstance(data, list):
        return []

    out: list[EditCandidate] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        suggested = str(item.get("suggested") or "").strip()
        if not suggested:
            continue
        out.append(EditCandidate(suggested=suggested, reason=str(item.get("reason") or "").strip()))
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def _normalize(s: str) -> str:
    """比对用的归一化：去空白（含全角空格）与常见排版差异。

    选区来自 DS 编辑器，`\\r\\n`、制表符、不间断空格都可能与 python-docx
    读出的段落文本不一致；严格逐字比对会让定位大面积失败。
    """
    return re.sub(r"[\s\u00a0\u3000]+", "", s or "")


def compute_context(full_text: str, selection: str, *, window: int = CONTEXT_WINDOW) -> tuple[str, str]:
    """在段落全文中定位选区，切出前后文。

    定位用归一化比对（见 `_normalize`）：原文按字面找不到时，退一步在
    归一化后的串里找位置，再按比例映射回原文下标。找不到就返回空上下文——
    上下文只是给模型的辅助信息，缺了不影响改写，不该因此让整次请求失败。
    """
    if not selection or not full_text:
        return "", ""
    idx = full_text.find(selection)
    if idx < 0:
        norm_full = _normalize(full_text)
        norm_sel = _normalize(selection)
        npos = norm_full.find(norm_sel)
        if npos < 0:
            return "", ""
        # 归一化删掉了空白，位置只能近似：按比例映射回原串长度
        ratio = len(full_text) / max(len(norm_full), 1)
        approx = int(npos * ratio)
        idx = max(0, min(approx, len(full_text) - 1))
        end = min(len(full_text), idx + int(len(norm_sel) * ratio))
    else:
        end = idx + len(selection)
    return full_text[max(0, idx - window) : idx], full_text[end : end + window]


class DirectEditor:
    """划词直改的候选生成器（无状态，除 LLM 服务）。"""

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm = llm_service or get_llm_service()

    def suggest(
        self,
        *,
        selection: str,
        instruction: str,
        context_before: str = "",
        context_after: str = "",
        model_name: str = "",
    ) -> list[EditCandidate]:
        """生成 2~3 条改写候选。不写盘、不建任务。"""
        sel = (selection or "").strip()
        inst = (instruction or "").strip()
        if not sel:
            raise ValidationException(message="选区为空，请先在文档里框选要修改的内容", errors={"selection": ""})
        if not inst:
            raise ValidationException(message="请说明要怎么改这一段", errors={"instruction": ""})
        if len(sel) > MAX_SELECTION_CHARS:
            raise ValidationException(
                message=f"选区过长（{len(sel)} 字），单次最多 {MAX_SELECTION_CHARS} 字；整段重构请走合同审查",
                errors={"selection": str(len(sel))},
            )

        prompt = build_rewrite_prompt(
            selection=sel,
            instruction=inst,
            context_before=context_before,
            context_after=context_after,
        )
        resp = self._llm.complete(
            prompt=prompt,
            model=model_name or None,
            # 比审查（0.3）更高：要多条取向不同的候选，全低温会让三条几乎同义
            temperature=0.7,
            max_tokens=8192,
            fallback=True,
        )
        candidates = parse_candidates(getattr(resp, "content", "") or "")
        if not candidates:
            raise ValidationException(message="AI 未能给出可用的改写结果，请调整要求后重试")
        return candidates


def get_direct_editor() -> DirectEditor:
    """工厂（供 API 层调用；测试可注入假 LLM）。"""
    return DirectEditor()


__all__ = [
    "CONTEXT_WINDOW",
    "MAX_CANDIDATES",
    "MAX_SELECTION_CHARS",
    "DirectEditor",
    "EditCandidate",
    "build_rewrite_prompt",
    "compute_context",
    "get_direct_editor",
    "parse_candidates",
]
