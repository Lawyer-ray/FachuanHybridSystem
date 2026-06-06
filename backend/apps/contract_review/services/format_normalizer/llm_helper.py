"""
LLM辅助服务
用于判断合同段落的层级结构
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ContractStructureAnalyzer:
    """合同结构分析器"""

    def __init__(self):
        from apps.core.llm.service import LLMService
        # 直接使用LLMService，它会自动读取后台配置的key
        self.llm_service = LLMService()

    def analyze_paragraph_level(self, text: str, context: str = "", llm_backend: str = "siliconflow") -> dict[str, Any]:
        """
        使用LLM分析段落的层级

        Args:
            text: 段落文本
            context: 上下文（前后段落）
            llm_backend: 使用的LLM后端（siliconflow/ollama）

        Returns:
            包含level和reason的字典
        """
        prompt = f"""段落：{text}

层级判断（直接返回JSON）：
0=一级标题 1=二级标题 2=三级标题 -1=正文

返回格式：{{"level":0,"reason":"理由"}}"""

        try:
            # 调用LLMService，使用openai_compatible后端（mimo2.5pro）
            # 不传递backend参数，让它使用默认后端
            response = self.llm_service.complete(
                prompt=prompt,
                system_prompt="你是一个专业的法律文档分析专家，擅长识别文档的层级结构。",
                temperature=0.3,
                max_tokens=200  # 增加token数量
            )

            # 解析响应（使用content属性）
            result_text = response.content.strip() if hasattr(response, 'content') else response.text.strip()

            # 尝试提取JSON（忽略其他文字）
            if "{" in result_text and "}" in result_text:
                # 找到JSON部分
                start = result_text.find("{")
                end = result_text.rfind("}") + 1
                json_str = result_text[start:end]

                try:
                    result = json.loads(json_str)
                    return {
                        "level": result.get("level", -1),
                        "reason": result.get("reason", "无法判断")
                    }
                except json.JSONDecodeError:
                    logger.warning(f"JSON解析失败: {json_str}")
                    return {"level": -1, "reason": "JSON解析失败"}
            else:
                logger.warning(f"LLM响应中没有找到JSON: {result_text[:100]}...")
                return {"level": -1, "reason": "LLM响应中没有找到JSON"}

        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return {"level": -1, "reason": f"LLM调用失败: {e}"}

    def analyze_paragraph_levels_batch(self, paragraphs: list[dict]) -> list[dict]:
        """
        批量分析段落层级

        Args:
            paragraphs: 段落列表，每个元素包含index和text

        Returns:
            包含level信息的段落列表
        """
        # 构建上下文
        texts = [p["text"] for p in paragraphs]
        context = "段落列表：" + " | ".join(texts[:10])  # 只取前10个作为上下文

        results = []
        for para in paragraphs:
            result = self.analyze_paragraph_level(para["text"], context)
            results.append({
                "index": para["index"],
                "text": para["text"],
                "level": result["level"],
                "reason": result["reason"]
            })

        return results

