"""
LLM辅助服务 - 合同结构分析

核心策略：
1. 一次性将所有段落发给 LLM，返回分类 + 手动前缀检测
2. 不确定的段落自动多轮验证（追加上下文）
3. 失败时 fallback 到简单规则
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: 一轮批量的段落数上限（再多 prompt 就长到容易超时/被截断）
_BATCH_SIZE = 20

#: 占位条目（LLM 少返 / 返回畸形）的置信度。必须 < 第二轮复审阈值 0.7，
#: 让这个位置在 `analyze_document` 的第二轮被重新判一次，而不是当成正常结论落下去。
_PLACEHOLDER_CONFIDENCE = 0.0


def _placeholder(reason: str) -> dict[str, Any]:
    """占位条目：层级按正文、置信度 0 强制进第二轮复审。"""
    return {"level": 1, "prefix": "", "confidence": _PLACEHOLDER_CONFIDENCE, "reason": reason}


def _coerce_int(value: Any) -> int | None:
    """把 LLM 给的整数（int / float / 纯数字字符串）转成 int；转不动返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return None
    return None


def _coerce_confidence(value: Any) -> float:
    """置信度必须是数字才能和复审阈值比较；缺失/畸形一律按 0（= 需要复审）。"""
    if isinstance(value, bool) or value is None:
        return _PLACEHOLDER_CONFIDENCE
    try:
        return float(value)
    except (TypeError, ValueError):
        return _PLACEHOLDER_CONFIDENCE


def _normalize_item(item: Any) -> dict[str, Any]:
    """把单个 LLM 条目规整成 ``{level:int, prefix:str, confidence:float, reason:str}``。

    S27-10（2026-11-23 二轮审计）：原实现在 `_parse_response` 里只校验「外层是
    list」，元素是字符串/数组、或 ``level`` 是字符串都原样交给下游——
    ``r.get("confidence")`` 抛 AttributeError（宽 except 兜成整篇回落关键词规则）、
    ``"400" if level < 2`` 抛 TypeError（整次规范化直接失败）。现在逐元素校验并转型。

    形状不对时返回**占位条目而不是丢弃**：调用方按位置把结果对回段落，
    少一个元素会让其后所有段落整体错位。
    """
    if not isinstance(item, dict):
        return _placeholder("LLM返回元素不是对象")
    level = _coerce_int(item.get("level"))
    if level is None or not 0 <= level <= 2:
        return _placeholder("LLM返回的level不可用")
    prefix = item.get("prefix")
    normalized: dict[str, Any] = {
        "level": level,
        "prefix": "" if prefix is None else str(prefix),
        "confidence": _coerce_confidence(item.get("confidence")),
        "reason": str(item.get("reason") or ""),
    }
    # index 只有第二轮（_refine_uncertain）按它回填，第一轮缺它不影响对位
    index = _coerce_int(item.get("index"))
    if index is not None:
        normalized["index"] = index
    return normalized


def _normalize_items(items: list[Any]) -> list[dict[str, Any]]:
    """逐个规整且**保持长度与顺序**（理由见 `_normalize_item` 的错位说明）。"""
    return [_normalize_item(item) for item in items]


class ContractStructureAnalyzer:  # pragma: no cover
    """合同结构分析器 - LLM 驱动"""

    def __init__(self, backend: str | None = None):  # pragma: no cover
        from apps.core.llm.service import LLMService

        self.llm_service = LLMService()
        self.backend = backend  # None = 自动选择可用后端
        self._cache: dict[str, Any] = {}

    # ── 批量分析（主入口） ──────────────────────────────────

    def analyze_document(  # pragma: no cover
        self,
        paragraphs: list[str],
        max_rounds: int = 2,
    ) -> list[dict[str, Any]]:
        """分析整个文档的段落结构

        Args:
            paragraphs: 段落文本列表（已 strip）
            max_rounds: 最大验证轮数

        Returns:
            每个段落的分析结果列表:
            [{"level": 0-2, "prefix": "一、" | "", "confidence": 0.0-1.0, "reason": "..."}]
        """
        cache_key = "|".join(paragraphs)
        if cache_key in self._cache:
            return self._cache[cache_key]  # type: ignore[no-any-return]

        # 第一轮：批量分析
        results = self._analyze_batch(paragraphs)

        # 第二轮：对低置信度的段落，追加上下文重新验证
        if max_rounds >= 2:
            uncertain = [i for i, r in enumerate(results) if r.get("confidence", 1.0) < 0.7]
            if uncertain:
                results = self._refine_uncertain(paragraphs, results, uncertain)

        self._cache[cache_key] = results
        return results

    # ── 第一轮：批量分析 ────────────────────────────────────

    def _analyze_batch(self, paragraphs: list[str]) -> list[dict[str, Any]]:  # pragma: no cover
        """一次性分析所有段落（LLM 失败时直接抛异常）"""
        # 每段前面带 [i]：这是判定「哪条结果对应哪一段」的唯一依据
        numbered = [f"[{i}] {text}" for i, text in enumerate(paragraphs)]

        # 分批处理（避免 prompt 过长导致超时）
        # S27-09（2026-11-23 二轮审计）：原实现把每批结果按顺序盲拼、最后按总长度
        # 补齐——只要某一批少返几条，其后所有段落整体前移（标题当正文、编号层级
        # /缩进/加粗全篇串位），补齐又把缺的伪装成「正文」。现在逐批按 index 对位，
        # 缺/错位的位置留占位并记 warning。
        all_results: list[dict[str, Any]] = []

        for batch_start in range(0, len(paragraphs), _BATCH_SIZE):
            batch = numbered[batch_start : batch_start + _BATCH_SIZE]
            batch_results = self._call_llm(
                "\n".join(batch),
                round_num=1,
                total_paragraphs=len(paragraphs),
            )
            all_results.extend(self._align_batch(batch_start, len(batch), batch_results))

        return all_results

    def _align_batch(
        self, batch_start: int, batch_len: int, batch_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """把一批 LLM 结果按 ``index`` 对回该批的段落位置（绝对下标 = batch_start + 批内偏移）。

        条目没带 index 时退化为「按返回顺序对应」——那正是 prompt 要求的作答顺序。
        结果只影响本批：某一批少返几条，后面的批次仍从自己的 batch_start 起算，
        不会像原来那样把错位传递到全篇。
        """
        aligned: list[dict[str, Any] | None] = [None] * batch_len
        # 至少得有一条 index 落在本批窗口内，才敢按 index 对位：有的模型会对每批
        # 重新从 0 编号，照 index 硬对会把整批判成越界、整批变成占位
        by_index = any(
            isinstance(item.get("index"), int) and 0 <= item["index"] - batch_start < batch_len
            for item in batch_results
        )
        unusable = 0
        for position, item in enumerate(batch_results):
            absolute = item.get("index")
            offset = absolute - batch_start if by_index and isinstance(absolute, int) else position
            if 0 <= offset < batch_len and aligned[offset] is None:
                aligned[offset] = item
            else:
                unusable += 1

        missing = sum(1 for item in aligned if item is None)
        if unusable or missing:
            logger.warning(
                "LLM 结构分析批次不齐：段落 [%d,%d) 返回 %d 条（按 index 对位=%s），错位/越界 %d 条，缺 %d 条"
                "（缺的占位并进第二轮复审）",
                batch_start,
                batch_start + batch_len,
                len(batch_results),
                by_index,
                unusable,
                missing,
            )
        return [item if item is not None else _placeholder("LLM未返回该段落") for item in aligned]

    def _call_llm(  # pragma: no cover
        self, paragraphs_text: str, round_num: int = 1, total_paragraphs: int = 0
    ) -> list[dict[str, Any]]:
        """调用 LLM 分析段落"""
        # 输入每段前缀 [i] 原样回填成 index：没有 index 就只能按返回顺序猜对位，
        # 一旦某批少返几条，后面全部错位（S27-09）
        system_prompt = """你是合同文档格式分析专家。分析每个段落的层级和手动编号前缀。

层级：0=一级标题(章节标题), 1=正文(条款内容), 2=子项(列表项)
手动编号前缀：如"一、"、"（一）"、"1、"、"(1)"等，没有则返回""

输入每一段前面都带一个 [编号]，请把该编号原样写进结果的 index 字段，
且输入的每个编号都必须有一条结果，不许省略。

严格按以下格式返回JSON数组，不要返回其他任何文字：
[{"index":0,"level":0,"prefix":"","confidence":0.9,"reason":"标题"}]"""

        prompt = f"分析以下{total_paragraphs}个段落：\n\n{paragraphs_text}"

        try:
            kwargs: dict[str, Any] = {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": 0.1,
                "max_tokens": 8000,
                "timeout": 120,
            }
            if self.backend:
                kwargs["backend"] = self.backend

            # 带重试的 LLM 调用（处理临时网络/API 问题）
            import time

            last_error = None
            for attempt in range(3):
                try:
                    response = self.llm_service.complete(**kwargs)
                    results = self._parse_response(response.content)
                    if not results:
                        raise RuntimeError("LLM 返回空结果")
                    return results
                except Exception as retry_err:
                    last_error = retry_err
                    if attempt < 2:
                        logger.warning("LLM 调用失败 (attempt %d/3), 重试中...", attempt + 1)
                        time.sleep(2 * (attempt + 1))
            raise last_error  # type: ignore[misc]
        except Exception as e:
            logger.error("LLM 批量分析失败: %s", e)
            raise  # 向上抛出，让调用方走 fallback

    # ── 第二轮：多轮验证 ────────────────────────────────────

    def _refine_uncertain(  # pragma: no cover
        self,
        paragraphs: list[str],
        results: list[dict[str, Any]],
        uncertain_indices: list[int],
    ) -> list[dict[str, Any]]:
        """对低置信度段落追加上下文重新分析"""
        if not uncertain_indices:
            return results

        # 构建上下文丰富的 prompt
        context_items = []
        for idx in uncertain_indices:
            # 取前后各 3 段作为上下文
            start = max(0, idx - 3)
            end = min(len(paragraphs), idx + 4)
            context_lines = []
            for j in range(start, end):
                marker = ">>>" if j == idx else "   "
                context_lines.append(f"{marker} [{j}] {paragraphs[j]}")

            context_items.append(
                f"--- 段落 [{idx}]（上一轮判断: level={results[idx]['level']}, "
                f"confidence={results[idx].get('confidence', 0)}）---\n" + "\n".join(context_lines)
            )

        system_prompt = """你是一个专业的中文合同文档格式分析专家。
以下是一些需要你重新审查的段落，每段都附带了前后文上下文。
请重新判断每个段落的层级和手动编号前缀。

标记 >>> 的是需要你判断的段落。

层级：0=一级标题, 1=正文, 2=子项
手动编号前缀：如"一、"、"（一）"、"1、"、"(1)"等，没有则返回 ""

返回 JSON 数组（每个段落一个元素）：
[{"index": 0, "level": 1, "prefix": "", "confidence": 0.9, "reason": "..."}]

只返回 JSON 数组。"""

        prompt = "请重新审查以下段落：\n\n" + "\n\n".join(context_items)

        try:
            response = self.llm_service.complete(
                prompt=prompt,
                system_prompt=system_prompt,
                backend=self.backend,
                temperature=0.2,
                max_tokens=4000,
            )
            refined = self._parse_response(response.content)

            # 合并结果
            for item in refined:
                idx = item.get("index")
                if idx is not None and 0 <= idx < len(results):
                    results[idx] = {
                        "level": item.get("level", results[idx]["level"]),
                        "prefix": item.get("prefix", results[idx].get("prefix", "")),
                        "confidence": item.get("confidence", 0.8),
                        "reason": item.get("reason", "第二轮验证"),
                    }
        except Exception as e:
            logger.warning("第二轮验证失败: %s", e)

        return results

    # ── 响应解析 ─────────────────────────────────────────────

    def _parse_response(self, text: str) -> list[dict[str, Any]]:  # pragma: no cover
        """解析 LLM 响应中的 JSON。

        S27-10（2026-11-23 二轮审计）：原实现只判「外层是 list」就原样返回，
        元素类型/必填键一律不校验，非 dict 元素或字符串 level 会在下游炸掉。
        现在每个出口都过一遍 `_normalize_items`。
        """
        text = text.strip()

        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return _normalize_items(result)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 数组
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                result = json.loads(text[start : end + 1])
                if isinstance(result, list):
                    return _normalize_items(result)
            except json.JSONDecodeError:
                pass

        # 尝试逐行解析（某些 LLM 会返回每行一个 JSON）
        results: list[Any] = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    obj = json.loads(line.rstrip(","))
                    results.append(obj)
                except json.JSONDecodeError:
                    continue
        if results:
            return _normalize_items(results)

        logger.warning("LLM 响应解析失败: %s...", text[:200])
        return []

    # ── 兼容旧接口 ──────────────────────────────────────────

    def analyze_paragraph_level(  # pragma: no cover
        self, text: str, context: str = "", llm_backend: str = "openai_compatible"
    ) -> dict[str, Any]:
        """单段落分析（兼容旧接口）"""
        results = self.analyze_document([text], max_rounds=1)
        if results:
            r = results[0]
            return {"level": r["level"], "reason": r.get("reason", "")}
        return {"level": -1, "reason": "分析失败"}

    def analyze_paragraph_levels_batch(  # pragma: no cover
        self, paragraphs: list[dict]
    ) -> list[dict[str, Any]]:
        """批量分析（兼容旧接口）"""
        texts = [p["text"] for p in paragraphs]
        results = self.analyze_document(texts)
        return [
            {
                "index": p["index"],
                "text": p["text"],
                "level": r["level"],
                "reason": r.get("reason", ""),
            }
            for p, r in zip(paragraphs, results)
        ]
