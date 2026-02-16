"""Business logic services."""

import re
from typing import Any, ClassVar


class PartyCandidateExtractor:
    _RECEIVER_PATTERN = re.compile(r"】\s*([^,,]{2,50})[,,]")
    _COMPANY_PATTERN = re.compile(r"[\u4e00-\u9fa5]{2,30}(?:有限责任公司|股份有限公司|有限公司|集团|企业)")
    _CHINESE_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fa5]{2,8}")

    _STOPWORDS: ClassVar = {
        "法院",
        "人民法院",
        "中级法院",
        "高级法院",
        "最高法院",
        "书记员",
        "法官",
        "平台",
        "系统",
        "通知",
        "送达",
        "执行",
        "立案",
        "短信",
    }

    def extract(self, content: str, *, max_candidates: int = 12) -> list[str]:
        if not content:
            return []

        candidates: list[str] = []
        candidates.extend(self._extract_receiver_names(content))
        candidates.extend(self._COMPANY_PATTERN.findall(content))

        if len(candidates) < max_candidates:
            candidates.extend(self._extract_chinese_tokens(content, max_candidates - len(candidates)))

        return self._deduplicate(candidates, max_candidates)

    def _extract_receiver_names(self, content: str) -> list[str]:
        """从短信开头提取收件人姓名"""
        results: list[Any] = []
        for name in self._RECEIVER_PATTERN.findall(content[:120]):
            cleaned = self._clean(name)
            if cleaned:
                results.append(cleaned)
        return results

    def _extract_chinese_tokens(self, content: str, limit: int) -> list[str]:
        """从短信开头提取中文词组"""
        results: list[Any] = []
        for token in self._CHINESE_TOKEN_PATTERN.findall(content[:120]):
            cleaned = self._clean(token)
            if cleaned:
                results.append(cleaned)
            if len(results) >= limit:
                break
        return results

    def _deduplicate(self, candidates: list[str], max_count: int) -> list[str]:
        """去重并限制数量"""
        out: list[str] = []
        seen = set()
        for cand in candidates:
            if cand not in seen:
                seen.add(cand)
                out.append(cand)
                if len(out) >= max_count:
                    break
        return out

    def _clean(self, text: str) -> str:
        name = (text or "").strip()
        if len(name) < 2:
            return ""
        for w in self._STOPWORDS:
            if w in name:
                return ""
        return name
