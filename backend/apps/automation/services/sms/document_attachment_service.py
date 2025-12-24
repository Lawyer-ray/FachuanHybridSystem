"""
文书附件服务

负责处理文书路径获取、重命名、添加附件等操作。
从 CourtSMSService 中解耦出来的文书附件处理逻辑。
"""
import os
import re
import shutil
import logging
from typing import List, Optional, Tuple
from django.conf import settings

from apps.core.exceptions import ValidationException, NotFoundError
from apps.core.interfaces import ServiceLocator

logger = logging.getLogger("apps.automation")


class DocumentAttachmentService:
    """文书附件服务 - 处理文书路径获取、重命名、添加附件"""
    
    def __init__(
        self,
        case_service: Optional["ICaseService"] = None,
        renamer: Optional["DocumentRenamer"] = None,
    ):
        """
        初始化服务，支持依赖注入
        
        Args:
            case_service: 案件服务（可选）
            renamer: 文书重命名服务（可选）
        """
        self._case_service = case_service
        self._renamer = renamer
    
    @property
    def case_service(self) -> "ICaseService":
        """延迟加载案件服务"""
        if self._case_service is None:
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service
    
    @property
    def renamer(self) -> "DocumentRenamer":
        """延迟加载重命名服务"""
        if self._renamer is None:
            from .document_renamer import DocumentRenamer
            self._renamer = DocumentRenamer()
        return self._renamer
    
    def get_paths_for_renaming(self, sms: "CourtSMS") -> List[str]:
        """
        获取待重命名的文书路径列表
        
        优先从 CourtDocument 记录获取，如果没有则从 ScraperTask.result 获取
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            文书文件路径列表
        """
        document_paths = []
        
        try:
            if not sms.scraper_task:
                logger.info(f"短信 {sms.id} 无下载任务，返回空路径列表")
                return document_paths
            
            # 方式1：从 CourtDocument 记录获取（优先）
            if hasattr(sms.scraper_task, 'documents'):
                documents = sms.scraper_task.documents.filter(download_status='success')
                for doc in documents:
                    if doc.local_file_path and os.path.exists(doc.local_file_path):
                        document_paths.append(doc.local_file_path)
                        logger.debug(f"从 CourtDocument 获取路径: {doc.local_file_path}")
            
            # 方式2：如果没有从数据库获取到，尝试从任务结果中获取（降级）
            if not document_paths:
                result = sms.scraper_task.result
                if result and isinstance(result, dict):
                    files = result.get('files', [])
                    for file_path in files:
                        if file_path and os.path.exists(file_path):
                            document_paths.append(file_path)
                            logger.debug(f"从 ScraperTask.result 获取路径: {file_path}")
                    
                    if files and not document_paths:
                        logger.warning(f"任务结果中有 {len(files)} 个文件路径，但都不存在")
            
            logger.info(f"获取到 {len(document_paths)} 个待重命名的文书路径")
            
        except Exception as e:
            logger.warning(f"获取文书路径失败: {str(e)}")
        
        return document_paths
    
    def get_paths_for_notification(self, sms: "CourtSMS") -> List[str]:
        """
        获取待发送通知的文书路径列表
        
        优先从 scraper_task.result['renamed_files'] 获取重命名后的路径
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            文书文件路径列表（已去重）
        """
        document_paths = []
        seen_paths = set()  # 用于去重
        
        try:
            if not sms.scraper_task:
                logger.info(f"短信 {sms.id} 无下载任务，返回空路径列表")
                return document_paths
            
            # 优先从任务结果中获取重命名后的文件路径
            result = sms.scraper_task.result
            if result and isinstance(result, dict):
                # 方式1：优先使用 renamed_files（重命名后的路径）
                renamed_files = result.get('renamed_files', [])
                if renamed_files:
                    for file_path in renamed_files:
                        if file_path and os.path.exists(file_path):
                            abs_path = os.path.abspath(file_path)
                            if abs_path not in seen_paths:
                                document_paths.append(file_path)
                                seen_paths.add(abs_path)
                                logger.debug(f"从 renamed_files 获取路径: {file_path}")
                    
                    if document_paths:
                        logger.info(f"从 renamed_files 获取到 {len(document_paths)} 个文书路径")
                        return document_paths
            
            # 方式2：从 CourtDocument 记录获取
            if hasattr(sms.scraper_task, 'documents'):
                documents = sms.scraper_task.documents.filter(download_status='success')
                for doc in documents:
                    if doc.local_file_path and os.path.exists(doc.local_file_path):
                        abs_path = os.path.abspath(doc.local_file_path)
                        if abs_path not in seen_paths:
                            document_paths.append(doc.local_file_path)
                            seen_paths.add(abs_path)
                            logger.debug(f"从 CourtDocument 获取路径: {doc.local_file_path}")
            
            # 方式3：从原始 files 列表获取
            if not document_paths and result and isinstance(result, dict):
                files = result.get('files', [])
                for file_path in files:
                    if file_path and os.path.exists(file_path):
                        abs_path = os.path.abspath(file_path)
                        if abs_path not in seen_paths:
                            document_paths.append(file_path)
                            seen_paths.add(abs_path)
                            logger.debug(f"从原始 files 获取路径: {file_path}")
            
            logger.info(f"获取到 {len(document_paths)} 个待发送通知的文书路径（已去重）")
            
        except Exception as e:
            logger.warning(f"获取通知文书路径失败: {str(e)}")
        
        return document_paths
    
    def rename_documents(
        self, 
        sms: "CourtSMS", 
        document_paths: List[str]
    ) -> List[str]:
        """
        重命名文书列表，返回重命名后的路径
        
        使用 DocumentRenamer 对每个文件进行重命名，处理重命名失败的情况
        
        Args:
            sms: CourtSMS 实例
            document_paths: 待重命名的文书路径列表
            
        Returns:
            重命名后的文书路径列表
        """
        if not document_paths:
            logger.info(f"短信 {sms.id} 无文书需要重命名")
            return []
        
        case_name = sms.case.name if sms.case else "未知案件"
        received_date = sms.received_at.date()
        renamed_paths = []
        
        logger.info(f"开始重命名 {len(document_paths)} 个文书: SMS ID={sms.id}")
        
        for file_path in document_paths:
            try:
                if not os.path.exists(file_path):
                    logger.warning(f"文书文件不存在，跳过: {file_path}")
                    continue
                
                # 获取原始文件名用于降级
                original_name = os.path.basename(file_path)
                
                # 使用带降级方案的重命名
                new_path = self.renamer.rename_with_fallback(
                    file_path,
                    case_name,
                    received_date,
                    original_name=original_name
                )
                
                renamed_paths.append(new_path)
                logger.info(f"文书重命名成功: {file_path} -> {new_path}")
                
            except Exception as e:
                logger.warning(f"文书重命名失败，保持原名: {file_path}, 错误: {str(e)}")
                # 重命名失败不影响流程，继续使用原路径
                if os.path.exists(file_path):
                    renamed_paths.append(file_path)
        
        logger.info(f"文书重命名完成: SMS ID={sms.id}, 成功重命名 {len(renamed_paths)} 个文书")
        return renamed_paths
    
    def add_to_case_log(self, sms: "CourtSMS", file_paths: List[str]) -> bool:
        """
        将文书附件添加到案件日志
        
        通过复制文件到目标目录并直接设置文件路径，避免 Django 自动生成随机后缀。
        
        Args:
            sms: CourtSMS 实例
            file_paths: 文书文件路径列表
            
        Returns:
            是否成功添加附件
        """
        if not sms.case_log or not file_paths:
            logger.warning(f"短信 {sms.id} 没有案件日志或文件路径，无法添加附件")
            return False
        
        try:
            success_count = 0
            
            # 目标目录：MEDIA_ROOT/case_logs/
            target_dir = os.path.join(settings.MEDIA_ROOT, 'case_logs')
            os.makedirs(target_dir, exist_ok=True)
            
            for file_path in file_paths:
                try:
                    if not os.path.exists(file_path):
                        logger.warning(f"文件不存在，跳过: {file_path}")
                        continue
                    
                    # 获取重命名后的文件名（已经是正确格式）
                    renamed_filename = os.path.basename(file_path)
                    
                    # 检查文件名是否符合预期格式（包含括号）
                    if '（' not in renamed_filename or '）' not in renamed_filename:
                        # 如果重命名没有成功，尝试手动生成正确的文件名
                        logger.warning(f"文件名格式不正确，尝试修正: {renamed_filename}")
                        renamed_filename = self.fix_filename_format(renamed_filename, sms)
                    
                    # 确保文件名不会太长
                    max_name_length = 200
                    if len(renamed_filename) > max_name_length:
                        name_part, ext = os.path.splitext(renamed_filename)
                        if not ext:
                            ext = '.pdf'
                        name_part = name_part[:max_name_length - len(ext)]
                        renamed_filename = name_part + ext
                    
                    # 构建目标文件路径
                    target_path = os.path.join(target_dir, renamed_filename)
                    
                    # 如果目标文件已存在，添加数字后缀（在"收"字后面）
                    if os.path.exists(target_path):
                        target_path, renamed_filename = self._get_unique_filepath(
                            target_dir, renamed_filename
                        )
                    
                    # 复制文件到目标目录
                    shutil.copy2(file_path, target_path)
                    
                    # 计算相对路径（相对于 MEDIA_ROOT）
                    relative_path = f"case_logs/{renamed_filename}"
                    
                    # 使用服务方法添加附件
                    success = self.case_service.add_case_log_attachment_internal(
                        case_log_id=sms.case_log.id,
                        file_path=relative_path,
                        file_name=renamed_filename
                    )
                    
                    if not success:
                        logger.warning(f"添加案件日志附件失败: {renamed_filename}")
                        continue
                    
                    success_count += 1
                    logger.info(f"成功添加文书附件到案件日志: {renamed_filename}")
                    
                except Exception as e:
                    logger.warning(f"添加文书附件失败: {file_path}, 错误: {str(e)}")
                    # 不影响整体流程，继续执行
            
            logger.info(f"附件添加完成: 成功 {success_count}/{len(file_paths)} 个")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"添加附件到案件日志失败: SMS ID={sms.id}, 错误: {str(e)}")
            return False
    
    def _get_unique_filepath(self, target_dir: str, filename: str) -> Tuple[str, str]:
        """
        获取唯一的文件路径，如果文件已存在则在"收"字后面添加数字后缀
        
        格式：标题（案件名称）_YYYYMMDD收.pdf -> 标题（案件名称）_YYYYMMDD收1.pdf
        
        Args:
            target_dir: 目标目录
            filename: 原始文件名
            
        Returns:
            tuple: (完整路径, 新文件名)
        """
        # 尝试在"收"字后面添加数字
        # 匹配模式：xxx收.pdf 或 xxx收N.pdf
        match = re.match(r'^(.+收)(\d*)\.(.+)$', filename)
        
        if match:
            base_name = match.group(1)  # xxx收
            existing_num = match.group(2)  # 可能为空或数字
            ext = match.group(3)  # pdf
            
            counter = 1
            if existing_num:
                counter = int(existing_num) + 1
            
            while True:
                new_filename = f"{base_name}{counter}.{ext}"
                new_path = os.path.join(target_dir, new_filename)
                if not os.path.exists(new_path):
                    return new_path, new_filename
                counter += 1
                if counter > 100:  # 防止无限循环
                    break
        
        # 降级方案：在扩展名前添加数字
        name_part, ext = os.path.splitext(filename)
        counter = 1
        while True:
            new_filename = f"{name_part}_{counter}{ext}"
            new_path = os.path.join(target_dir, new_filename)
            if not os.path.exists(new_path):
                return new_path, new_filename
            counter += 1
            if counter > 100:
                # 最后的降级：使用时间戳
                import time
                timestamp = int(time.time())
                new_filename = f"{name_part}_{timestamp}{ext}"
                new_path = os.path.join(target_dir, new_filename)
                return new_path, new_filename
    
    def fix_filename_format(self, filename: str, sms: "CourtSMS") -> str:
        """
        修正文件名格式，确保符合预期的格式：标题（案件名称）_YYYYMMDD收.pdf
        
        Args:
            filename: 原始文件名
            sms: CourtSMS 实例
            
        Returns:
            修正后的文件名
        """
        try:
            # 移除文件扩展名
            name_without_ext = filename
            if '.' in filename:
                name_without_ext = filename.rsplit('.', 1)[0]
            
            # 获取案件名称和日期
            case_name = sms.case.name if sms.case else "未知案件"
            received_date = sms.received_at.date()
            date_str = received_date.strftime("%Y%m%d")
            
            # 清理案件名称中的非法字符
            case_name = self._sanitize_filename_part(case_name)
            if len(case_name) > 30:
                case_name = case_name[:30]
            
            # 尝试从原文件名中提取标题
            title = "司法文书"  # 默认标题
            
            # 常见的文书类型模式
            title_patterns = [
                r'(诉讼费用交费通知书|交费通知书)',
                r'(受理案件通知书|案件受理通知书|受理通知书)',
                r'(诉讼权利义务告知书|权利义务告知书)',
                r'(诉讼风险告知书|风险告知书)',
                r'(小额诉讼告知书|诉讼告知书)',
                r'(判决书|裁定书|调解书|决定书|传票|通知书|支付令|告知书)'
            ]
            
            for pattern in title_patterns:
                match = re.search(pattern, name_without_ext)
                if match:
                    title = match.group(1)
                    break
            
            # 生成正确格式的文件名
            fixed_filename = f"{title}（{case_name}）_{date_str}收.pdf"
            
            logger.info(f"文件名格式修正: {filename} -> {fixed_filename}")
            return fixed_filename
            
        except Exception as e:
            logger.warning(f"修正文件名格式失败: {filename}, 错误: {str(e)}")
            # 返回一个基本的格式
            case_name = sms.case.name if sms.case else "未知案件"
            date_str = sms.received_at.strftime("%Y%m%d")
            return f"司法文书（{case_name}）_{date_str}收.pdf"
    
    def _sanitize_filename_part(self, text: str) -> str:
        """
        清理文件名部分，移除非法字符
        
        Args:
            text: 原始文本
            
        Returns:
            str: 清理后的文本
        """
        if not text:
            return ""
        
        # 移除或替换文件名中的非法字符
        # Windows 文件名非法字符: < > : " | ? * \ /
        illegal_chars = r'[<>:"|?*\\/]'
        text = re.sub(illegal_chars, '', text)
        
        # 移除英文括号，避免与中文括号混淆
        text = re.sub(r'[()]', '', text)
        
        # 移除控制字符
        text = re.sub(r'[\x00-\x1f\x7f]', '', text)
        
        # 移除首尾空格和点号
        text = text.strip(' .')
        
        return text
    
    def _find_renamed_file(self, original_path: str, sms: "CourtSMS") -> Optional[str]:
        """
        查找重命名后的文件
        
        当原始文件路径不存在时，尝试在同目录下查找重命名后的文件
        
        Args:
            original_path: 原始文件路径
            sms: CourtSMS 实例
            
        Returns:
            重命名后的文件路径，如果找不到则返回 None
        """
        import glob
        
        try:
            if not original_path:
                return None
            
            # 获取目录和案件名称
            directory = os.path.dirname(original_path)
            if not os.path.exists(directory):
                return None
            
            case_name = sms.case.name if sms.case else None
            if not case_name:
                return None
            
            # 在目录中查找包含案件名称的文件
            pattern = os.path.join(directory, f"*{case_name[:10]}*.pdf")
            matches = glob.glob(pattern)
            
            if matches:
                # 返回最新的文件
                matches.sort(key=os.path.getmtime, reverse=True)
                logger.info(f"找到重命名后的文件: {matches[0]}")
                return matches[0]
            
            return None
            
        except Exception as e:
            logger.warning(f"查找重命名文件失败: {str(e)}")
            return None