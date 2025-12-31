"""
文书类型分类器

调用 Ollama 大模型判断法院文书类型。

Requirements: 4.1, 4.2, 4.7
"""
import json
import logging
from typing import Optional, Tuple

from apps.core.exceptions import ServiceUnavailableError, RecognitionTimeoutError
from apps.automation.services.ai.ollama_client import chat
from apps.automation.services.ai import get_ollama_model, get_ollama_base_url
from apps.automation.services.court_document_recognition.data_classes import DocumentType

logger = logging.getLogger("apps.automation")


class DocumentClassifier:
    """
    文书类型分类器
    
    使用 Ollama 大模型分析文书内容，判断文书类型（传票/执行裁定书/其他）。
    
    Requirements: 4.1, 4.2
    """
    
    # 分类提示词模板
    CLASSIFICATION_PROMPT = """请分析以下法院文书内容，判断文书类型。

文书内容：
{text}

请判断这是以下哪种类型的文书：
1. summons - 传票（包含开庭时间、出庭通知等）
2. execution - 执行裁定书（包含财产保全、执行裁定等）
3. other - 其他类型文书

判断依据：
- 传票通常包含：开庭时间、出庭地点、案号、当事人信息
- 执行裁定书通常包含：财产保全、查封、冻结、执行裁定等关键词
- 如果无法确定或不属于以上两种，请返回 other

请严格按照以下 JSON 格式返回结果，不要包含其他内容：
{{"type": "summons|execution|other", "confidence": 0.0-1.0, "reason": "判断理由"}}
"""
    
    def __init__(
        self,
        ollama_model: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
    ):
        """
        初始化文书分类器
        
        Args:
            ollama_model: Ollama 模型名称，默认从配置读取
            ollama_base_url: Ollama 服务地址，默认从配置读取
        """
        self.ollama_model = ollama_model or get_ollama_model()
        self.ollama_base_url = ollama_base_url or get_ollama_base_url()
    
    def classify(self, text: str) -> Tuple[DocumentType, float]:
        """
        分类文书类型
        
        Args:
            text: 文书文本内容
            
        Returns:
            Tuple[DocumentType, float]: (文书类型, 置信度)
            
        Raises:
            ServiceUnavailableError: Ollama 服务不可用
            RecognitionTimeoutError: 分类超时
            RuntimeError: 分类过程中发生其他错误
        """
        if not text or not text.strip():
            logger.warning(
                "文书内容为空，返回 OTHER 类型",
                extra={"action": "classify", "result": "empty_text"}
            )
            return DocumentType.OTHER, 0.0
        
        # 截取文本前 3000 字符，避免超出模型上下文限制
        truncated_text = text[:3000] if len(text) > 3000 else text
        
        logger.info(
            f"开始分类文书",
            extra={
                "action": "classify",
                "text_length": len(text),
                "truncated_length": len(truncated_text)
            }
        )
        
        try:
            # 构建消息
            prompt = self.CLASSIFICATION_PROMPT.format(text=truncated_text)
            messages = [{"role": "user", "content": prompt}]
            
            # 调用 Ollama
            response = chat(
                model=self.ollama_model,
                messages=messages,
                base_url=self.ollama_base_url,
            )
            
            # 解析响应
            doc_type, confidence = self._parse_classification_response(response)
            
            logger.info(
                f"文书分类完成",
                extra={
                    "action": "classify",
                    "document_type": doc_type.value,
                    "confidence": confidence
                }
            )
            return doc_type, confidence
            
        except ConnectionError as e:
            logger.error(
                f"Ollama 服务不可用: {e}",
                extra={
                    "action": "classify",
                    "error_type": "connection_error",
                    "error": str(e)
                }
            )
            raise ServiceUnavailableError(
                message="AI 服务暂时不可用，请稍后重试",
                code="OLLAMA_SERVICE_UNAVAILABLE",
                errors={"service": "Ollama 服务连接失败"},
                service_name="Ollama"
            )
        except TimeoutError as e:
            logger.error(
                f"文书分类超时: {e}",
                extra={
                    "action": "classify",
                    "error_type": "timeout_error",
                    "error": str(e)
                }
            )
            raise RecognitionTimeoutError(
                message="文书分类超时，请重试",
                code="CLASSIFICATION_TIMEOUT",
                errors={"timeout": "AI 分类超时"}
            )
        except Exception as e:
            logger.error(
                f"文书分类失败: {str(e)}",
                extra={
                    "action": "classify",
                    "error_type": type(e).__name__,
                    "error": str(e)
                },
                exc_info=True
            )
            raise RuntimeError(f"文书分类失败: {str(e)}")
    
    def _parse_classification_response(
        self, 
        response: dict
    ) -> Tuple[DocumentType, float]:
        """
        解析 Ollama 分类响应
        
        Args:
            response: Ollama API 响应
            
        Returns:
            Tuple[DocumentType, float]: (文书类型, 置信度)
        """
        try:
            # 提取响应内容
            if "message" not in response or "content" not in response["message"]:
                logger.warning("Ollama 响应格式异常，返回 OTHER 类型")
                return DocumentType.OTHER, 0.0
            
            content = response["message"]["content"]
            
            # 尝试解析 JSON
            result = self._extract_json_from_response(content)
            
            if result is None:
                logger.warning(f"无法从响应中提取 JSON: {content[:200]}")
                return DocumentType.OTHER, 0.0
            
            # 提取类型
            type_str = result.get("type", "other").lower()
            doc_type = self._map_type_string(type_str)
            
            # 提取置信度
            confidence = float(result.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # 限制在 0-1 范围
            
            # 记录判断理由
            reason = result.get("reason", "")
            if reason:
                logger.debug(f"分类理由: {reason}")
            
            return doc_type, confidence
            
        except Exception as e:
            logger.warning(f"解析分类响应失败: {str(e)}")
            return DocumentType.OTHER, 0.0
    
    def _extract_json_from_response(self, content: str) -> Optional[dict]:
        """
        从响应内容中提取 JSON
        
        支持处理包含额外文本的响应。
        
        Args:
            content: 响应内容
            
        Returns:
            Optional[dict]: 解析出的 JSON 对象，失败返回 None
        """
        content = content.strip()
        
        # 直接尝试解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # 尝试提取 JSON 块
        # 查找 { 和 } 的位置
        start_idx = content.find("{")
        end_idx = content.rfind("}")
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = content[start_idx:end_idx + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # 尝试处理 markdown 代码块
        if "```json" in content:
            try:
                json_start = content.index("```json") + 7
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
                return json.loads(json_str)
            except (ValueError, json.JSONDecodeError):
                pass
        
        if "```" in content:
            try:
                json_start = content.index("```") + 3
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
                return json.loads(json_str)
            except (ValueError, json.JSONDecodeError):
                pass
        
        return None
    
    def _map_type_string(self, type_str: str) -> DocumentType:
        """
        将类型字符串映射为 DocumentType 枚举
        
        Args:
            type_str: 类型字符串
            
        Returns:
            DocumentType: 文书类型枚举
        """
        type_mapping = {
            "summons": DocumentType.SUMMONS,
            "传票": DocumentType.SUMMONS,
            "execution": DocumentType.EXECUTION_RULING,
            "执行裁定书": DocumentType.EXECUTION_RULING,
            "execution_ruling": DocumentType.EXECUTION_RULING,
            "other": DocumentType.OTHER,
            "其他": DocumentType.OTHER,
        }
        
        return type_mapping.get(type_str.lower(), DocumentType.OTHER)
