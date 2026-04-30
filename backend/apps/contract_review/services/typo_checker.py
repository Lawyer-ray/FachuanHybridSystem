from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from apps.core.llm.exceptions import LLMBackendUnavailableError
from apps.core.llm.service import LLMService

logger = logging.getLogger(__name__)


@dataclass
class TypoResult:
    original: str
    corrected: str
    paragraph_index: int


class TypoChecker:
    """通过 LLM 检测合同错别字"""

    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    def check_typos(self, paragraphs: list[str], model_name: str = "") -> list[TypoResult]:
        """分段发送给 LLM 检测错别字，返回结构化结果"""
        all_results: list[TypoResult] = []
        # 每次发送一批段落（避免超长）
        batch_size = 20
        for start in range(0, len(paragraphs), batch_size):
            batch = paragraphs[start : start + batch_size]
            text = "\n".join(f"[段落{start + i}] {p}" for i, p in enumerate(batch))
            prompt = self._build_prompt(text)
            try:
                resp = self._llm.complete(
                    prompt=prompt,
                    model=model_name or None,
                    temperature=0.1,
                    fallback=True,
                )
                results = self._parse_llm_response(resp.content)
                all_results.extend(results)
            except LLMBackendUnavailableError:
                raise  # LLM 不可用，直接向上抛终止任务
            except Exception:
                logger.exception("错别字检测解析失败 (段落 %d-%d)", start, start + len(batch))
        return all_results

    @staticmethod
    def _build_prompt(text: str) -> str:
        return (
            "你是一个专业的中文合同校对员。请检查以下合同文本中的错别字。\n"
            "每个段落前标注了段落编号 [段落N]。\n"
            "仅返回 JSON 数组，格式：\n"
            '[{"original": "错误文本", "corrected": "正确文本", "paragraph_index": 段落编号}]\n'
            "如果没有错别字，返回空数组 []。\n"
            "不要返回任何其他内容。\n\n"
            f"{text}"
        )

    @staticmethod
    def _parse_llm_response(response_text: str) -> list[TypoResult]:
        # 提取 JSON 部分
        text = response_text.strip()
        # 处理 markdown 代码块
        if "```" in text:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                text = text[start:end]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("错别字检测 JSON 解析失败: %s", text[:200])
            return []

        if not isinstance(data, list):
            return []

        results: list[TypoResult] = []
        for item in data:
            if isinstance(item, dict) and "original" in item and "corrected" in item:
                results.append(
                    TypoResult(
                        original=str(item["original"]),
                        corrected=str(item["corrected"]),
                        paragraph_index=_parse_int(item.get("paragraph_index", 0)),
                    )
                )
        return results


def _parse_int(val: object) -> int:
    """解析 LLM 返回的段落索引，兼容 '段落85'、85、'85' 等格式"""
    if isinstance(val, int):
        return val
    s = str(val).strip()
    import re

    m = re.search(r"\d+", s)
    return int(m.group()) if m else 0
