"""
Automation模块标准化日志工具类

提供结构化日志记录方法，确保所有日志都符合规范格式。
"""

import logging
import time
from typing import Dict, Any, Optional, Union
from datetime import datetime

logger = logging.getLogger(__name__)


class AutomationLogger:
    """Automation模块标准化日志工具类"""
    
    # ==================== 验证码相关日志 ====================
    
    @staticmethod
    def log_captcha_recognition_start(
        image_size: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录验证码识别开始"""
        extra = {
            "action": "captcha_recognition_start",
            "timestamp": datetime.now().isoformat(),
        }
        if image_size is not None:
            extra["image_size"] = image_size
        extra.update(kwargs)
        
        logger.info("开始验证码识别", extra=extra)
    
    @staticmethod
    def log_captcha_recognition_success(
        processing_time: float,
        result_length: int,
        image_size: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录验证码识别成功"""
        extra = {
            "action": "captcha_recognition_success",
            "success": True,
            "processing_time": processing_time,
            "result_length": result_length,
            "timestamp": datetime.now().isoformat(),
        }
        if image_size is not None:
            extra["image_size"] = image_size
        extra.update(kwargs)
        
        logger.info("验证码识别成功", extra=extra)
    
    @staticmethod
    def log_captcha_recognition_failed(
        processing_time: float,
        error_message: str,
        image_size: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录验证码识别失败"""
        extra = {
            "action": "captcha_recognition_failed",
            "success": False,
            "processing_time": processing_time,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
        }
        if image_size is not None:
            extra["image_size"] = image_size
        extra.update(kwargs)
        
        logger.error("验证码识别失败", extra=extra)
    
    # ==================== Token相关日志 ====================
    
    @staticmethod
    def log_token_acquisition_start(
        acquisition_id: str,
        site_name: str,
        account: Optional[str] = None,
        **kwargs
    ) -> None:
        """记录Token获取开始"""
        extra = {
            "action": "token_acquisition_start",
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "timestamp": datetime.now().isoformat(),
        }
        if account:
            extra["account"] = account
        extra.update(kwargs)
        
        logger.info("开始Token获取流程", extra=extra)
    
    @staticmethod
    def log_token_acquisition_success(
        acquisition_id: str,
        site_name: str,
        account: str,
        total_duration: float,
        **kwargs
    ) -> None:
        """记录Token获取成功"""
        extra = {
            "action": "token_acquisition_success",
            "success": True,
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": account,
            "total_duration": total_duration,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.info("Token获取成功", extra=extra)
    
    @staticmethod
    def log_token_acquisition_failed(
        acquisition_id: str,
        site_name: str,
        error_message: str,
        account: Optional[str] = None,
        total_duration: Optional[float] = None,
        **kwargs
    ) -> None:
        """记录Token获取失败"""
        extra = {
            "action": "token_acquisition_failed",
            "success": False,
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
        }
        if account:
            extra["account"] = account
        if total_duration is not None:
            extra["total_duration"] = total_duration
        extra.update(kwargs)
        
        logger.error("Token获取失败", extra=extra)
    
    @staticmethod
    def log_existing_token_used(
        acquisition_id: str,
        site_name: str,
        account: str,
        token_expires_at: Optional[str] = None,
        **kwargs
    ) -> None:
        """记录使用现有Token"""
        extra = {
            "action": "existing_token_used",
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": account,
            "timestamp": datetime.now().isoformat(),
        }
        if token_expires_at:
            extra["token_expires_at"] = token_expires_at
        extra.update(kwargs)
        
        logger.info("使用现有Token", extra=extra)
    
    # ==================== 登录相关日志 ====================
    
    @staticmethod
    def log_auto_login_start(
        acquisition_id: str,
        site_name: str,
        account: str,
        **kwargs
    ) -> None:
        """记录自动登录开始"""
        extra = {
            "action": "auto_login_start",
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": account,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.info("开始自动登录", extra=extra)
    
    @staticmethod
    def log_auto_login_success(
        acquisition_id: str,
        site_name: str,
        account: str,
        login_duration: float,
        **kwargs
    ) -> None:
        """记录自动登录成功"""
        extra = {
            "action": "auto_login_success",
            "success": True,
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": account,
            "login_duration": login_duration,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.info("自动登录成功", extra=extra)
    
    @staticmethod
    def log_auto_login_timeout(
        acquisition_id: str,
        site_name: str,
        account: str,
        timeout_seconds: int,
        login_duration: float,
        **kwargs
    ) -> None:
        """记录自动登录超时"""
        extra = {
            "action": "auto_login_timeout",
            "success": False,
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": account,
            "timeout_seconds": timeout_seconds,
            "login_duration": login_duration,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.error("自动登录超时", extra=extra)
    
    @staticmethod
    def log_login_retry(
        network_attempt: int,
        max_network_retries: int,
        captcha_attempt: Optional[int] = None,
        max_captcha_retries: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录登录重试"""
        extra = {
            "action": "login_retry",
            "network_attempt": network_attempt,
            "max_network_retries": max_network_retries,
            "timestamp": datetime.now().isoformat(),
        }
        if captcha_attempt is not None:
            extra["captcha_attempt"] = captcha_attempt
        if max_captcha_retries is not None:
            extra["max_captcha_retries"] = max_captcha_retries
        extra.update(kwargs)
        
        logger.info(f"登录重试 {network_attempt}/{max_network_retries}", extra=extra)
    
    # ==================== 文档相关日志 ====================
    
    @staticmethod
    def log_document_creation_start(
        scraper_task_id: int,
        case_id: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录文档创建开始"""
        extra = {
            "action": "document_creation_start",
            "scraper_task_id": scraper_task_id,
            "timestamp": datetime.now().isoformat(),
        }
        if case_id is not None:
            extra["case_id"] = case_id
        extra.update(kwargs)
        
        logger.info("开始创建文档记录", extra=extra)
    
    @staticmethod
    def log_document_creation_success(
        document_id: int,
        scraper_task_id: int,
        case_id: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录文档创建成功"""
        extra = {
            "action": "document_creation_success",
            "success": True,
            "document_id": document_id,
            "scraper_task_id": scraper_task_id,
            "timestamp": datetime.now().isoformat(),
        }
        if case_id is not None:
            extra["case_id"] = case_id
        extra.update(kwargs)
        
        logger.info("文档记录创建成功", extra=extra)
    
    @staticmethod
    def log_document_status_update(
        document_id: int,
        old_status: str,
        new_status: str,
        **kwargs
    ) -> None:
        """记录文档状态更新"""
        extra = {
            "action": "document_status_update",
            "document_id": document_id,
            "old_status": old_status,
            "new_status": new_status,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.info("文档状态更新", extra=extra)
    
    # ==================== 文档处理相关日志 ====================
    
    @staticmethod
    def log_document_processing_start(
        file_type: str,
        file_size: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录文档处理开始"""
        extra = {
            "action": "document_processing_start",
            "file_type": file_type,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        
        logger.info(f"开始处理{file_type}文档", extra=extra)
    
    @staticmethod
    def log_document_processing_success(
        file_type: str,
        processing_time: float,
        content_length: int,
        file_size: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录文档处理成功"""
        extra = {
            "action": "document_processing_success",
            "success": True,
            "file_type": file_type,
            "processing_time": processing_time,
            "content_length": content_length,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        
        logger.info(f"{file_type}文档处理成功", extra=extra)
    
    @staticmethod
    def log_document_processing_failed(
        file_type: str,
        error_message: str,
        processing_time: float,
        file_size: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录文档处理失败"""
        extra = {
            "action": "document_processing_failed",
            "success": False,
            "file_type": file_type,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        
        logger.error(f"{file_type}文档处理失败", extra=extra)
    
    # ==================== AI相关日志 ====================
    
    @staticmethod
    def log_ai_filename_generation_start(
        content_length: int,
        **kwargs
    ) -> None:
        """记录AI文件名生成开始"""
        extra = {
            "action": "ai_filename_generation_start",
            "content_length": content_length,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.info("开始AI文件名生成", extra=extra)
    
    @staticmethod
    def log_ai_filename_generation_success(
        generated_filename: str,
        processing_time: float,
        content_length: int,
        **kwargs
    ) -> None:
        """记录AI文件名生成成功"""
        extra = {
            "action": "ai_filename_generation_success",
            "success": True,
            "generated_filename": generated_filename,
            "processing_time": processing_time,
            "content_length": content_length,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.info("AI文件名生成成功", extra=extra)
    
    @staticmethod
    def log_ai_filename_generation_failed(
        error_message: str,
        processing_time: float,
        content_length: int,
        **kwargs
    ) -> None:
        """记录AI文件名生成失败"""
        extra = {
            "action": "ai_filename_generation_failed",
            "success": False,
            "error_message": error_message,
            "processing_time": processing_time,
            "content_length": content_length,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.error("AI文件名生成失败", extra=extra)
    
    # ==================== 语音相关日志 ====================
    
    @staticmethod
    def log_audio_transcription_start(
        file_format: str,
        file_size: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录音频转录开始"""
        extra = {
            "action": "audio_transcription_start",
            "file_format": file_format,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        
        logger.info("开始音频转录", extra=extra)
    
    @staticmethod
    def log_audio_transcription_success(
        transcription_length: int,
        processing_time: float,
        file_format: str,
        file_size: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录音频转录成功"""
        extra = {
            "action": "audio_transcription_success",
            "success": True,
            "transcription_length": transcription_length,
            "processing_time": processing_time,
            "file_format": file_format,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        
        logger.info("音频转录成功", extra=extra)
    
    @staticmethod
    def log_audio_transcription_failed(
        error_message: str,
        processing_time: float,
        file_format: str,
        file_size: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录音频转录失败"""
        extra = {
            "action": "audio_transcription_failed",
            "success": False,
            "error_message": error_message,
            "processing_time": processing_time,
            "file_format": file_format,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        
        logger.error("音频转录失败", extra=extra)
    
    # ==================== 性能监控相关日志 ====================
    
    @staticmethod
    def log_performance_metrics_collection_start(
        metric_type: str,
        **kwargs
    ) -> None:
        """记录性能指标收集开始"""
        extra = {
            "action": "performance_metrics_collection_start",
            "metric_type": metric_type,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.debug(f"开始收集{metric_type}性能指标", extra=extra)
    
    @staticmethod
    def log_performance_metrics_collection_success(
        metric_type: str,
        metrics_count: int,
        collection_time: float,
        **kwargs
    ) -> None:
        """记录性能指标收集成功"""
        extra = {
            "action": "performance_metrics_collection_success",
            "success": True,
            "metric_type": metric_type,
            "metrics_count": metrics_count,
            "collection_time": collection_time,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.debug(f"{metric_type}性能指标收集成功", extra=extra)
    
    @staticmethod
    def log_performance_metrics_collection_failed(
        metric_type: str,
        error_message: str,
        collection_time: float,
        **kwargs
    ) -> None:
        """记录性能指标收集失败"""
        extra = {
            "action": "performance_metrics_collection_failed",
            "success": False,
            "metric_type": metric_type,
            "error_message": error_message,
            "collection_time": collection_time,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.error(f"{metric_type}性能指标收集失败", extra=extra)
    
    @staticmethod
    def log_performance_metric_recorded(
        metric_name: str,
        value: Union[int, float],
        **kwargs
    ) -> None:
        """记录性能指标记录"""
        extra = {
            "action": "performance_metric_recorded",
            "metric_name": metric_name,
            "value": value,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.info(f"性能指标记录: {metric_name} = {value}", extra=extra)
    
    # ==================== Admin操作相关日志 ====================
    
    @staticmethod
    def log_admin_operation_start(
        operation: str,
        user_id: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录Admin操作开始"""
        extra = {
            "action": "admin_operation_start",
            "operation": operation,
            "timestamp": datetime.now().isoformat(),
        }
        if user_id is not None:
            extra["user_id"] = user_id
        extra.update(kwargs)
        
        logger.info(f"开始Admin操作: {operation}", extra=extra)
    
    @staticmethod
    def log_admin_operation_success(
        operation: str,
        affected_count: int,
        processing_time: float,
        user_id: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录Admin操作成功"""
        extra = {
            "action": "admin_operation_success",
            "success": True,
            "operation": operation,
            "affected_count": affected_count,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if user_id is not None:
            extra["user_id"] = user_id
        extra.update(kwargs)
        
        logger.info(f"Admin操作成功: {operation}", extra=extra)
    
    @staticmethod
    def log_admin_operation_failed(
        operation: str,
        error_message: str,
        processing_time: float,
        user_id: Optional[int] = None,
        **kwargs
    ) -> None:
        """记录Admin操作失败"""
        extra = {
            "action": "admin_operation_failed",
            "success": False,
            "operation": operation,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if user_id is not None:
            extra["user_id"] = user_id
        extra.update(kwargs)
        
        logger.error(f"Admin操作失败: {operation}", extra=extra)
    
    # ==================== 通用业务日志 ====================
    
    @staticmethod
    def log_business_operation(
        operation: str,
        resource_type: str,
        resource_id: Optional[Union[int, str]] = None,
        user_id: Optional[int] = None,
        success: bool = True,
        **kwargs
    ) -> None:
        """记录通用业务操作"""
        extra = {
            "action": "business_operation",
            "operation": operation,
            "resource_type": resource_type,
            "success": success,
            "timestamp": datetime.now().isoformat(),
        }
        if resource_id is not None:
            extra["resource_id"] = resource_id
        if user_id is not None:
            extra["user_id"] = user_id
        extra.update(kwargs)
        
        log_level = logger.info if success else logger.error
        log_level(f"业务操作: {operation} {resource_type}", extra=extra)
    
    @staticmethod
    def log_cross_module_call(
        source_module: str,
        target_module: str,
        service_name: str,
        method_name: str,
        **kwargs
    ) -> None:
        """记录跨模块调用"""
        extra = {
            "action": "cross_module_call",
            "source_module": source_module,
            "target_module": target_module,
            "service_name": service_name,
            "method_name": method_name,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.debug(f"跨模块调用: {source_module} -> {target_module}.{service_name}.{method_name}", extra=extra)


    # ==================== 文书送达 API 相关日志 ====================
    
    @staticmethod
    def log_document_api_request_start(
        api_name: str,
        page_num: Optional[int] = None,
        page_size: Optional[int] = None,
        sdbh: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        记录文书 API 请求开始
        
        Requirements: 7.1
        """
        extra = {
            "action": "document_api_request_start",
            "api_name": api_name,
            "timestamp": datetime.now().isoformat(),
        }
        if page_num is not None:
            extra["page_num"] = page_num
        if page_size is not None:
            extra["page_size"] = page_size
        if sdbh is not None:
            extra["sdbh"] = sdbh
        extra.update(kwargs)
        
        logger.info(f"开始调用文书API: {api_name}", extra=extra)
    
    @staticmethod
    def log_document_api_request_success(
        api_name: str,
        response_code: int,
        processing_time: float,
        document_count: Optional[int] = None,
        total_count: Optional[int] = None,
        page_num: Optional[int] = None,
        **kwargs
    ) -> None:
        """
        记录文书 API 请求成功
        
        Requirements: 7.1, 7.2
        """
        extra = {
            "action": "document_api_request_success",
            "success": True,
            "api_name": api_name,
            "response_code": response_code,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if document_count is not None:
            extra["document_count"] = document_count
        if total_count is not None:
            extra["total_count"] = total_count
        if page_num is not None:
            extra["page_num"] = page_num
        extra.update(kwargs)
        
        logger.info(f"文书API调用成功: {api_name}", extra=extra)
    
    @staticmethod
    def log_document_api_request_failed(
        api_name: str,
        error_message: str,
        processing_time: float,
        response_code: Optional[int] = None,
        page_num: Optional[int] = None,
        **kwargs
    ) -> None:
        """
        记录文书 API 请求失败
        
        Requirements: 7.1, 7.4
        """
        extra = {
            "action": "document_api_request_failed",
            "success": False,
            "api_name": api_name,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if response_code is not None:
            extra["response_code"] = response_code
        if page_num is not None:
            extra["page_num"] = page_num
        extra.update(kwargs)
        
        logger.error(f"文书API调用失败: {api_name}", extra=extra)
    
    @staticmethod
    def log_document_query_statistics(
        total_found: int,
        processed_count: int,
        skipped_count: int,
        failed_count: int,
        query_method: str = "api",
        credential_id: Optional[int] = None,
        **kwargs
    ) -> None:
        """
        记录文书查询统计信息
        
        Requirements: 7.2
        """
        extra = {
            "action": "document_query_statistics",
            "total_found": total_found,
            "processed_count": processed_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "query_method": query_method,
            "timestamp": datetime.now().isoformat(),
        }
        if credential_id is not None:
            extra["credential_id"] = credential_id
        extra.update(kwargs)
        
        logger.info(
            f"文书查询统计: 发现={total_found}, 处理={processed_count}, "
            f"跳过={skipped_count}, 失败={failed_count}",
            extra=extra
        )
    
    @staticmethod
    def log_document_download_start(
        document_name: str,
        url: Optional[str] = None,
        sdbh: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        记录文书下载开始
        
        Requirements: 7.1
        """
        extra = {
            "action": "document_download_start",
            "document_name": document_name,
            "timestamp": datetime.now().isoformat(),
        }
        if url is not None:
            # 只记录 URL 前缀，避免泄露签名信息
            extra["url_prefix"] = url[:50] + "..." if len(url) > 50 else url
        if sdbh is not None:
            extra["sdbh"] = sdbh
        extra.update(kwargs)
        
        logger.info(f"开始下载文书: {document_name}", extra=extra)
    
    @staticmethod
    def log_document_download_success(
        document_name: str,
        file_size: int,
        processing_time: float,
        save_path: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        记录文书下载成功
        
        Requirements: 7.1, 7.2
        """
        extra = {
            "action": "document_download_success",
            "success": True,
            "document_name": document_name,
            "file_size": file_size,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if save_path is not None:
            extra["save_path"] = save_path
        extra.update(kwargs)
        
        logger.info(f"文书下载成功: {document_name}", extra=extra)
    
    @staticmethod
    def log_document_download_failed(
        document_name: str,
        error_message: str,
        processing_time: float,
        **kwargs
    ) -> None:
        """
        记录文书下载失败
        
        Requirements: 7.1, 7.4
        """
        extra = {
            "action": "document_download_failed",
            "success": False,
            "document_name": document_name,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        
        logger.error(f"文书下载失败: {document_name}", extra=extra)
    
    @staticmethod
    def log_fallback_triggered(
        from_method: str,
        to_method: str,
        reason: str,
        error_type: Optional[str] = None,
        credential_id: Optional[int] = None,
        **kwargs
    ) -> None:
        """
        记录降级触发
        
        Requirements: 7.3
        """
        extra = {
            "action": "fallback_triggered",
            "from_method": from_method,
            "to_method": to_method,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        }
        if error_type is not None:
            extra["error_type"] = error_type
        if credential_id is not None:
            extra["credential_id"] = credential_id
        extra.update(kwargs)
        
        logger.warning(f"降级触发: {from_method} -> {to_method}, 原因: {reason}", extra=extra)
    
    @staticmethod
    def log_api_error_detail(
        api_name: str,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        request_params: Optional[Dict[str, Any]] = None,
        response_data: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """
        记录 API 详细错误信息
        
        Requirements: 7.4
        """
        extra = {
            "action": "api_error_detail",
            "api_name": api_name,
            "error_type": error_type,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
        }
        if stack_trace is not None:
            extra["stack_trace"] = stack_trace
        if request_params is not None:
            # 过滤敏感信息
            safe_params = {k: v for k, v in request_params.items() if k not in ["token", "password"]}
            extra["request_params"] = safe_params
        if response_data is not None:
            extra["response_data"] = response_data
        extra.update(kwargs)
        
        logger.error(f"API错误详情: {api_name} - {error_type}: {error_message}", extra=extra)
