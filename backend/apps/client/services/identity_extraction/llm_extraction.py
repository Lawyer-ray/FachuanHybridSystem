"""LLM 结构化提取与 JSON 解析。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.client.services.wiring import get_llm_service
from apps.core.exceptions import ServiceUnavailableError
from apps.core.llm.exceptions import LLMNetworkError, LLMTimeoutError

from .data_classes import LLMExtractionError
from .prompts import get_prompt_for_doc_type
from .text_cleaning import _prepare_text_for_llm, _sanitize_pii_for_log

logger = logging.getLogger(__name__)


def _llm_extract(raw_text: str, doc_type: str, model: str) -> dict[str, Any]:  # pragma: no cover
    """使用 LLM 从文字中提取结构化信息。"""
    try:
        llm_text = _prepare_text_for_llm(raw_text)
        logger.info("发送 LLM 前 OCR 文本清洗完成: 原始长度=%d, 清洗后长度=%d", len(raw_text), len(llm_text))
        logger.debug("发送 LLM 前 OCR 清洗后文本内容(脱敏截断): %s", _sanitize_pii_for_log(llm_text))

        prompt = get_prompt_for_doc_type(doc_type, llm_text)
        # 推理模型需要更多 token（reasoning + output），普通模型 512 足够
        max_tokens = 2048
        logger.info(
            "证件识别将调用 LLM: model=%s, max_tokens=%s",
            model,
            max_tokens,
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"请从以下文字中提取信息:\n{llm_text}"},
        ]

        llm_service = get_llm_service()
        llm_resp = llm_service.chat(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            timeout=60,
            think=False,
            fallback=True,
        )
        logger.debug(
            "LLM 响应详情(内容脱敏截断): backend=%s, model=%s, content=%s, prompt_tokens=%s, completion_tokens=%s",
            llm_resp.backend,
            llm_resp.model,
            _sanitize_pii_for_log(str(llm_resp.content)),
            llm_resp.prompt_tokens,
            llm_resp.completion_tokens,
        )
        content = llm_resp.content or ""
        if not content:
            raise LLMExtractionError(_("LLM 返回内容为空"))

        # 解析 JSON
        try:
            extracted_data = _parse_llm_json(content)
            logger.info("LLM 提取成功,字段数量: %s", len(extracted_data))
            return dict(extracted_data)

        except (json.JSONDecodeError, ValueError) as e:
            logger.exception("LLM 返回的 JSON 格式错误: %s", e)
            raise LLMExtractionError(_("智能识别结果解析失败，请稍后重试")) from e

    except ConnectionError as e:
        logger.exception("LLM 服务连接失败: %s", e)
        raise ServiceUnavailableError(message=_("LLM 服务连接失败: %(e)s") % {"e": e}, service_name="LLM") from e
    except LLMTimeoutError as e:
        logger.warning("LLM 请求超时: %s", e)
        raise LLMExtractionError(_("智能识别超时，请稍后重试")) from e
    except LLMNetworkError as e:
        logger.warning("LLM 网络异常: %s", e)
        raise LLMExtractionError(_("无法连接智能识别服务，请检查网络后重试")) from e
    except LLMExtractionError:
        raise
    except Exception as e:
        logger.exception("LLM 提取失败: %s", e)
        raise LLMExtractionError(_("智能识别暂时不可用，请稍后重试")) from e


def _parse_llm_json(content: str) -> dict[str, Any]:
    r"""从 LLM 输出中提取 JSON 对象，支持多种格式。

    与权威实现 ``apps.core.llm.structured_output.extract_json_text`` 的差异
    （2026-11 实测，以下 3 条均使得本函数**有意**保留独立版本）：

    1. **失败语义不同**：本函数在解析不出对象时抛 ``ValueError``，调用方据此
       转换成 ``LLMExtractionError(_("智能识别结果解析失败，请稍后重试"))``；
       权威实现返回 ``None``。替换会把异常路径静默改成 `None` 分支。
    2. **只取非嵌套对象**：最后一步用窄正则 ``\{[^{}]*\}``，嵌套对象
       （如 ``'x {"a":{"b":1}} y'``）取不到，会抛 ``ValueError``；
       权威实现能正确取出嵌套对象。这是历史行为，调用方依赖失败走重试文案。
    3. **围栏优先级高于直接解析**：本函数先试 ```json 块、再试整串直解；
       权威实现先试整串。同一段文本里两者可能返回不同 JSON。

    结论：需求是「统一到唯一实现」，但这里改就是改业务异常语义与抽取结果，
    不属于纯去重，故保留并在调用方不变的前提下维持现状。
    """
    # 1. 尝试从 ```json ... ``` 代码块中提取
    if "```json" in content:
        json_start = content.find("```json") + 7
        json_end = content.find("```", json_start)
        if json_end > json_start:
            result: dict[str, Any] = json.loads(content[json_start:json_end].strip())
            return result
    # 2. 尝试从 ``` ... ``` 代码块中提取
    if "```" in content:
        json_start = content.find("```") + 3
        json_end = content.find("```", json_start)
        if json_end > json_start:
            result2: dict[str, Any] = json.loads(content[json_start:json_end].strip())
            return result2
    # 3. 尝试直接解析整个内容
    try:
        result3: dict[str, Any] = json.loads(content.strip())
        return result3
    except json.JSONDecodeError:
        pass
    # 4. 尝试从文本中提取第一个 JSON 对象
    match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
    if match:
        result4: dict[str, Any] = json.loads(match.group())
        return result4
    raise ValueError("无法从 LLM 输出中提取 JSON")
