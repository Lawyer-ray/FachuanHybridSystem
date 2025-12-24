"""
案号提取服务

负责从法院文书中提取案号并同步到案件。
从 CourtSMSService 中解耦出来的独立服务。
"""
import logging
import re
from typing import Optional, List, TYPE_CHECKING

from apps.core.interfaces import ServiceLocator

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService, IDocumentProcessingService

logger = logging.getLogger("apps.automation")


class CaseNumberExtractorService:
    """
    案号提取服务
    
    职责：
    1. 从文书中提取案号（使用 Ollama AI）
    2. 验证和规范化案号
    3. 同步案号到案件
    
    支持依赖注入，遵循项目架构规范。
    """
    
    def __init__(
        self,
        document_processing_service: Optional["IDocumentProcessingService"] = None,
        case_service: Optional["ICaseService"] = None,
    ):
        """
        初始化服务，支持依赖注入
        
        Args:
            document_processing_service: 文档处理服务（可选）
            case_service: 案件服务（可选）
        """
        self._document_processing_service = document_processing_service
        self._case_service = case_service
    
    @property
    def document_processing_service(self) -> "IDocumentProcessingService":
        """延迟加载文档处理服务"""
        if self._document_processing_service is None:
            self._document_processing_service = ServiceLocator.get_document_processing_service()
        return self._document_processing_service
    
    @property
    def case_service(self) -> "ICaseService":
        """延迟加载案件服务"""
        if self._case_service is None:
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service
    
    def extract_from_document(self, document_path: str) -> List[str]:
        """
        从文书中提取案号（使用 Ollama AI）
        
        Args:
            document_path: 文书文件路径
            
        Returns:
            案号列表（已规范化、去重）
        """
        if not document_path:
            logger.warning("文书路径为空，无法提取案号")
            return []
        
        try:
            # 读取 PDF 内容
            logger.info(f"开始从文书提取内容: {document_path}")
            result = self.document_processing_service.extract_document_content_by_path_internal(
                document_path, 
                limit=3000  # 限制字符数以提高处理效率
            )
            
            if not result or not result.get("text"):
                logger.warning(f"无法从文书中提取文本内容: {document_path}")
                return []
            
            content = result["text"].strip()
            if not content:
                logger.warning(f"文书内容为空: {document_path}")
                return []
            
            # 删除空格（PDF 提取的内容可能包含多余空格，影响 Ollama 识别）
            original_len = len(content)
            content = content.replace(" ", "").replace("\u3000", "")  # 删除半角和全角空格
            logger.info(f"从文书中提取到 {original_len} 字符的内容，删除空格后为 {len(content)} 字符")
            
            # 使用 Ollama 提取案号
            extracted_numbers = self.extract_from_content(content)
            
            if extracted_numbers:
                logger.info(f"从文书成功提取案号: {document_path}, 案号: {extracted_numbers}")
            else:
                logger.warning(f"从文书未提取到案号: {document_path}")
                # 记录文书内容的前500字符用于调试
                logger.debug(f"文书内容预览（前500字符）: {content[:500]}")
            
            return extracted_numbers
            
        except ConnectionError as e:
            logger.error(f"Ollama 服务不可用，无法从文书提取案号: {document_path}, 错误: {str(e)}")
            return []
        except FileNotFoundError as e:
            logger.error(f"文书文件不存在: {document_path}, 错误: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"从文书提取案号失败: {document_path}, 错误: {str(e)}")
            return []
    
    def extract_from_content(self, content: str) -> List[str]:
        """
        从文本内容中提取案号（使用 Ollama AI）
        
        Args:
            content: 文书文本内容
            
        Returns:
            案号列表（已规范化、去重）
        """
        if not content or not content.strip():
            logger.warning("文书内容为空，无法提取案号")
            return []
        
        try:
            from apps.automation.services.ai.ollama_client import chat
            from apps.automation.services.ai import get_ollama_model
            import json
            
            # 构建提示词
            prompt = f"""
请从以下法律文书内容中提取所有案号。

案号格式规则：
1. 标准格式：(年份)法院代码案件类型序号，如：(2024)粤0604民初12345号
2. 简化格式：法院代码案件类型序号，如：粤0604民初12345号
3. 可能包含全角字符，需要识别
4. 案号通常出现在文书开头或标题中

返回 JSON 格式：{{"case_numbers": ["案号1", "案号2"]}}
如果没有找到案号，返回：{{"case_numbers": []}}

文书内容：
{content}
"""
            
            logger.info("开始调用 Ollama 提取案号")
            model = get_ollama_model()
            messages = [
                {"role": "user", "content": prompt}
            ]
            
            response = chat(model, messages)
            
            if not response or "message" not in response:
                logger.warning("Ollama 返回空响应")
                return []
            
            content_text = response["message"].get("content", "")
            logger.info(f"Ollama 案号提取响应: {content_text}")
            
            # 尝试解析 JSON 响应
            try:
                # 提取 JSON 部分（可能包含其他文本）
                start_idx = content_text.find("{")
                end_idx = content_text.rfind("}") + 1
                
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = content_text[start_idx:end_idx]
                    result = json.loads(json_str)
                    
                    if isinstance(result, dict) and "case_numbers" in result:
                        case_numbers = result["case_numbers"]
                        if isinstance(case_numbers, list):
                            # 验证格式有效性、规范化并去重
                            validated_numbers = self.validate_and_normalize(case_numbers)
                            
                            if validated_numbers:
                                logger.info(f"Ollama 成功提取案号: {validated_numbers}")
                            else:
                                logger.info("Ollama 未提取到有效案号")
                            return validated_numbers
                
                logger.warning(f"Ollama 返回格式不正确，尝试降级方案: {content_text[:100]}...")
                
                # 处理 Ollama 返回非标准格式的情况
                return self._extract_fallback(content_text)
                
            except json.JSONDecodeError as e:
                logger.warning(f"解析 Ollama JSON 响应失败，尝试降级方案: {str(e)}")
                
                # 处理 Ollama 返回非标准格式的情况
                return self._extract_fallback(content_text)
                
        except ConnectionError as e:
            logger.error(f"Ollama 服务不可用: {str(e)}")
            return []
        except ImportError as e:
            logger.error(f"无法导入 Ollama 相关模块: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"使用 Ollama 提取案号失败: {str(e)}")
            return []
    
    def validate_and_normalize(self, case_numbers: List[str]) -> List[str]:
        """
        验证案号格式有效性并规范化
        
        支持的格式：
        1. 标准案号格式：(2024)粤0604民初12345号
        2. 简化案号格式：粤0604民初12345号
        3. 包含全角字符的案号
        
        Args:
            case_numbers: 原始案号列表
            
        Returns:
            验证通过并规范化的案号列表（已去重）
        """
        if not case_numbers:
            logger.debug("案号列表为空，无需验证")
            return []
        
        try:
            from apps.cases.services.case_number_service import CaseNumberService
            
            valid_numbers = []
            seen = set()
            
            # 案号格式验证正则
            # 标准格式：(年份)法院代码案件类型序号
            standard_pattern = r'^\（\d{4}\）[^）]*?\w+\d+[^0-9]*?\d+号$'
            # 简化格式：法院代码案件类型序号
            simple_pattern = r'^[^（）]*?\w+\d+[^0-9]*?\d+号$'
            
            logger.info(f"开始验证 {len(case_numbers)} 个案号")
            
            for i, case_number in enumerate(case_numbers):
                try:
                    if not case_number or not isinstance(case_number, str):
                        logger.warning(f"案号 {i+1} 无效（空值或非字符串）: {case_number}")
                        continue
                    
                    original_number = case_number.strip()
                    if not original_number:
                        logger.warning(f"案号 {i+1} 为空字符串，跳过")
                        continue
                    
                    # 使用 CaseNumberService 规范化
                    try:
                        normalized_number = CaseNumberService.normalize_case_number(original_number)
                    except Exception as e:
                        logger.warning(f"案号规范化失败: {original_number}, 错误: {str(e)}")
                        continue
                    
                    if not normalized_number:
                        logger.warning(f"案号规范化后为空，跳过: {original_number}")
                        continue
                    
                    # 验证格式
                    try:
                        is_valid = (
                            re.match(standard_pattern, normalized_number) or 
                            re.match(simple_pattern, normalized_number)
                        )
                    except re.error as e:
                        logger.warning(f"案号格式验证失败: {normalized_number}, 正则错误: {str(e)}")
                        continue
                    
                    if is_valid:
                        if normalized_number not in seen:
                            valid_numbers.append(normalized_number)
                            seen.add(normalized_number)
                            logger.debug(f"案号验证通过: {original_number} -> {normalized_number}")
                        else:
                            logger.debug(f"案号重复，跳过: {normalized_number}")
                    else:
                        logger.warning(f"案号格式不正确，跳过: {original_number} -> {normalized_number}")
                        
                except Exception as e:
                    logger.warning(f"处理案号 {i+1} 时发生错误: {case_number}, 错误: {str(e)}")
                    continue
            
            logger.info(f"案号验证完成: 输入 {len(case_numbers)} 个，有效 {len(valid_numbers)} 个")
            return valid_numbers
            
        except ImportError as e:
            logger.error(f"无法导入必要模块进行案号验证: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"案号验证和规范化失败: {str(e)}")
            return []
    
    def sync_to_case(self, case_id: int, case_numbers: List[str], sms_id: int) -> int:
        """
        同步案号到案件
        
        检查案件中是否已存在该案号，不存在则写入。
        
        Args:
            case_id: 案件 ID
            case_numbers: 案号列表
            sms_id: 短信 ID（用于备注）
            
        Returns:
            成功写入的案号数量
        """
        if not case_id:
            logger.warning("案件 ID 为空，无法同步案号")
            return 0
        
        if not case_numbers:
            logger.info(f"没有案号需要同步: Case ID={case_id}")
            return 0
        
        try:
            from apps.cases.services.case_number_service import CaseNumberService
            
            # 去重处理
            case_numbers_to_sync = self._deduplicate(case_numbers)
            
            if not case_numbers_to_sync:
                logger.info(f"去重后没有案号需要同步: Case ID={case_id}")
                return 0
            
            # 获取案件现有的案号（规范化后）
            try:
                existing_case_numbers = self.case_service.get_case_numbers_by_case_internal(case_id)
                existing_numbers = set()
                for cn in existing_case_numbers:
                    normalized = CaseNumberService.normalize_case_number(cn)
                    if normalized:
                        existing_numbers.add(normalized)
                
                logger.info(f"案件现有案号数量: {len(existing_numbers)}, Case ID={case_id}")
                
            except Exception as e:
                logger.error(f"获取案件现有案号失败: Case ID={case_id}, 错误: {str(e)}")
                return 0
            
            # 检查案号是否已存在，不存在则写入
            success_count = 0
            case_number_service = CaseNumberService()
            
            for case_number in case_numbers_to_sync:
                normalized_number = CaseNumberService.normalize_case_number(case_number)
                
                if not normalized_number:
                    logger.warning(f"案号格式不正确，跳过: {case_number}")
                    continue
                
                if normalized_number not in existing_numbers:
                    try:
                        case_number_service.create_number(
                            case_id=case_id,
                            number=normalized_number,
                            remarks=f"从法院短信自动提取 (SMS ID: {sms_id})"
                        )
                        
                        logger.info(f"案号写入成功: Case ID={case_id}, 案号={normalized_number}")
                        existing_numbers.add(normalized_number)  # 避免重复写入
                        success_count += 1
                        
                    except Exception as e:
                        logger.error(f"案号写入失败: Case ID={case_id}, 案号={normalized_number}, 错误: {str(e)}")
                else:
                    logger.info(f"案号已存在，跳过: Case ID={case_id}, 案号={normalized_number}")
            
            if success_count > 0:
                logger.info(f"案号同步完成: SMS ID={sms_id}, 成功写入 {success_count} 个案号")
            else:
                logger.info(f"案号同步完成: SMS ID={sms_id}, 无新案号需要写入")
            
            return success_count
                    
        except Exception as e:
            logger.error(f"同步案号失败: Case ID={case_id}, SMS ID={sms_id}, 错误: {str(e)}")
            return 0
    
    def _extract_fallback(self, response_text: str) -> List[str]:
        """
        降级方案：使用正则从响应中提取案号
        
        当 Ollama 返回非标准格式时使用
        
        Args:
            response_text: Ollama 的原始响应文本
            
        Returns:
            案号列表（已规范化、去重）
        """
        if not response_text or not response_text.strip():
            logger.warning("降级方案：响应文本为空")
            return []
        
        try:
            logger.info("使用降级方案从响应中提取案号")
            
            # 案号正则模式
            patterns = [
                # 标准格式：(2024)粤0604民初12345号
                r'\((\d{4})\)([^)]*?\w+\d+[^0-9]*?\d+号)',
                # 简化格式：粤0604民初12345号
                r'([^()\s]*?[0-9]+[^0-9]*?[0-9]+号)',
                # 更宽泛的模式
                r'(\w*\d+\w*\d+号)'
            ]
            
            found_numbers = []
            
            for i, pattern in enumerate(patterns):
                try:
                    matches = re.findall(pattern, response_text)
                    logger.debug(f"正则模式 {i+1} 匹配到 {len(matches)} 个结果")
                    
                    for match in matches:
                        if isinstance(match, tuple):
                            # 处理分组匹配
                            if len(match) == 2:
                                # 标准格式：重新组合
                                case_number = f"({match[0]}){match[1]}"
                            else:
                                case_number = match[0]
                        else:
                            case_number = match
                        
                        if case_number and case_number.strip():
                            found_numbers.append(case_number.strip())
                            
                except re.error as e:
                    logger.warning(f"正则模式 {i+1} 执行失败: {str(e)}")
                    continue
            
            if found_numbers:
                logger.info(f"降级方案原始提取结果: {found_numbers}")
            else:
                logger.warning("降级方案未匹配到任何案号模式")
            
            # 验证和规范化提取到的案号
            validated_numbers = self.validate_and_normalize(found_numbers)
            
            if validated_numbers:
                logger.info(f"降级方案成功提取案号: {validated_numbers}")
            else:
                logger.warning("降级方案未能提取到有效案号")
            
            return validated_numbers
            
        except Exception as e:
            logger.error(f"降级方案提取案号失败: {str(e)}")
            return []
    
    def _deduplicate(self, case_numbers: List[str]) -> List[str]:
        """
        去重处理案号列表
        
        Args:
            case_numbers: 案号列表
            
        Returns:
            去重后的案号列表
        """
        if not case_numbers:
            return []
        
        try:
            from apps.cases.services.case_number_service import CaseNumberService
            
            seen = set()
            unique_numbers = []
            
            for case_number in case_numbers:
                if not case_number or not isinstance(case_number, str):
                    continue
                
                # 规范化后再去重
                normalized = CaseNumberService.normalize_case_number(case_number.strip())
                
                if normalized and normalized not in seen:
                    unique_numbers.append(normalized)
                    seen.add(normalized)
            
            logger.debug(f"案号去重完成: 输入 {len(case_numbers)} 个，去重后 {len(unique_numbers)} 个")
            return unique_numbers
            
        except Exception as e:
            logger.error(f"案号去重失败: {str(e)}")
            return case_numbers  # 返回原始列表
