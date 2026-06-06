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

    def analyze_paragraph_level(self, text: str, context: str = "") -> dict[str, Any]:
        """
        使用LLM分析段落的层级

        Args:
            text: 段落文本
            context: 上下文（前后段落）

        Returns:
            包含level和reason的字典
        """
        prompt = f"""你是一个法律文档分析专家。请分析以下段落的层级结构。

段落文本：{text}

上下文：{context}

请判断这个段落属于哪个层级：
- level=0: 一级标题（如"服务内容"、"费用"、"保密义务"等主要章节）
- level=1: 二级标题（如具体的服务项目、费用明细等）
- level=2: 三级标题（如具体的操作步骤、细节说明等）
- level=-1: 正文内容（不是标题）

请以JSON格式返回：
{{
    "level": 0/1/2/-1,
    "reason": "判断理由"
}}

只返回JSON，不要有其他内容。"""

        try:
            # 直接调用LLMService，指定使用siliconflow后端（mimo2.5pro）
            response = self.llm_service.complete(
                prompt=prompt,
                system_prompt="你是一个专业的法律文档分析专家，擅长识别文档的层级结构。",
                temperature=0.3,
                max_tokens=100,
                backend="siliconflow"  # 指定使用siliconflow后端
            )

            # 解析响应
            result_text = response.text.strip()

            # 尝试提取JSON
            if "{" in result_text and "}" in result_text:
                # 找到JSON部分
                start = result_text.find("{")
                end = result_text.rfind("}") + 1
                json_str = result_text[start:end]

                result = json.loads(json_str)
                return {
                    "level": result.get("level", -1),
                    "reason": result.get("reason", "无法判断")
                }
            else:
                logger.warning(f"LLM响应格式错误: {result_text}")
                return {"level": -1, "reason": "LLM响应格式错误"}

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

