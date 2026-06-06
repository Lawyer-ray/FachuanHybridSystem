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


class ContractStructureAnalyzer:
    """合同结构分析器 - LLM 驱动"""

    def __init__(self, backend: str = "siliconflow"):
        from apps.core.llm.service import LLMService

        self.llm_service = LLMService()
        self.backend = backend
        self._cache: dict[str, Any] = {}

    # ── 批量分析（主入口） ──────────────────────────────────

    def analyze_document(
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
            return self._cache[cache_key]

        # 第一轮：批量分析
        results = self._analyze_batch(paragraphs)

        # 第二轮：对低置信度的段落，追加上下文重新验证
        if max_rounds >= 2:
            uncertain = [
                i for i, r in enumerate(results)
                if r.get("confidence", 1.0) < 0.7
            ]
            if uncertain:
                results = self._refine_uncertain(paragraphs, results, uncertain)

        self._cache[cache_key] = results
        return results

    # ── 第一轮：批量分析 ────────────────────────────────────

    def _analyze_batch(self, paragraphs: list[str]) -> list[dict[str, Any]]:
        """一次性分析所有段落（LLM 失败时直接抛异常）"""
        # 构建带编号的段落列表
        numbered = []
        for i, text in enumerate(paragraphs):
            numbered.append(f"[{i}] {text}")

        # 分批处理（避免 prompt 过长）
        batch_size = 80
        all_results: list[dict[str, Any]] = []

        for batch_start in range(0, len(paragraphs), batch_size):
            batch = numbered[batch_start : batch_start + batch_size]
            batch_results = self._call_llm(
                "\n".join(batch),
                round_num=1,
                total_paragraphs=len(paragraphs),
            )
            all_results.extend(batch_results)

        # 补齐（如果 LLM 返回的数量不匹配）
        while len(all_results) < len(paragraphs):
            all_results.append(
                {"level": 1, "prefix": "", "confidence": 0.3, "reason": "LLM未返回"}
            )

        return all_results[: len(paragraphs)]

    def _call_llm(
        self, paragraphs_text: str, round_num: int = 1, total_paragraphs: int = 0
    ) -> list[dict[str, Any]]:
        """调用 LLM 分析段落"""
        system_prompt = """你是一个专业的中文合同文档格式分析专家。

你的任务是分析合同文档的段落，判断每个段落在文档结构中的层级，并检测手动编号前缀。

层级定义：
- 0 = 一级标题/章节标题（如"服务内容"、"合作期限"、"保密义务"、"权利与义务"）
- 1 = 正文/条款内容（正常叙述段落）
- 2 = 子项/列表项（隶属于某个章节下的细分条目）

手动编号前缀检测：
- 如果段落以手动编号开头（如"一、"、"（一）"、"1、"、"(1)"、"第X条"等），返回该前缀文本
- 如果没有手动编号前缀，prefix 返回空字符串 ""

返回格式：一个 JSON 数组，每个元素对应一个段落：
[{"level": 0, "prefix": "一、", "confidence": 0.95, "reason": "章节标题"}]

confidence 表示你的判断置信度（0.0-1.0），低于 0.7 的会在第二轮被重新审查。
只返回 JSON 数组，不要返回其他文字。"""

        prompt = f"以下是合同文档的 {total_paragraphs} 个段落（带编号），请分析每个段落的层级和手动编号前缀：\n\n{paragraphs_text}"

        try:
            response = self.llm_service.complete(
                prompt=prompt,
                system_prompt=system_prompt,
                backend=self.backend,
                temperature=0.2,
                max_tokens=8000,
            )
            results = self._parse_response(response.content)
            if not results:
                raise RuntimeError("LLM 返回空结果")
            return results
        except Exception as e:
            logger.error("LLM 批量分析失败: %s", e)
            raise  # 向上抛出，让调用方走 fallback

    # ── 第二轮：多轮验证 ────────────────────────────────────

    def _refine_uncertain(
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
                f"confidence={results[idx].get('confidence', 0)}）---\n"
                + "\n".join(context_lines)
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

    def _parse_response(self, text: str) -> list[dict[str, Any]]:
        """解析 LLM 响应中的 JSON"""
        text = text.strip()

        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 数组
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                result = json.loads(text[start : end + 1])
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        # 尝试逐行解析（某些 LLM 会返回每行一个 JSON）
        results = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    obj = json.loads(line.rstrip(","))
                    results.append(obj)
                except json.JSONDecodeError:
                    continue
        if results:
            return results

        logger.warning("LLM 响应解析失败: %s...", text[:200])
        return []

    # ── 兼容旧接口 ──────────────────────────────────────────

    def analyze_paragraph_level(
        self, text: str, context: str = "", llm_backend: str = "siliconflow"
    ) -> dict[str, Any]:
        """单段落分析（兼容旧接口）"""
        results = self.analyze_document([text], max_rounds=1)
        if results:
            r = results[0]
            return {"level": r["level"], "reason": r.get("reason", "")}
        return {"level": -1, "reason": "分析失败"}

    def analyze_paragraph_levels_batch(
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
