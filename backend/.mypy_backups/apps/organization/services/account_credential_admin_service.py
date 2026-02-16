"""
AccountCredentialAdminService - 账号凭证管理服务
封装 Admin 层的业务逻辑，包括自动登录功能
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import NotFoundError

logger = logging.getLogger(__name__)


@dataclass
class LoginResult:
    """单次登录结果"""
    success: bool
    duration: float
    token: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class BatchLoginResult:
    """批量登录结果"""
    success_count: int
    error_count: int
    total_duration: float
    message: str


class AccountCredentialAdminService:
    """
    账号凭证管理服务 - 封装 Admin 层业务逻辑
    
    职责：
    - 批量自动登录
    - 单个账号自动登录
    - 记录登录历史
    """
    
    SUPPORTED_SITE = "court_zxfw"
    
    def __init__(self):
        self._auto_login_service = None
        self._token_service = None

    @property
    def auto_login_service(self):
        """延迟加载 AutoLoginService"""
        if self._auto_login_service is None:
            from apps.automation.services.token.auto_login_service import AutoLoginService
            self._auto_login_service = AutoLoginService()
        return self._auto_login_service
    
    @property
    def token_service(self):
        """延迟加载 AutoTokenAcquisitionService"""
        if self._token_service is None:
            from apps.automation.services.token.auto_token_acquisition_service import (
                AutoTokenAcquisitionService,
            )
            from apps.automation.services.token.account_selection_strategy import (
                AccountSelectionStrategy,
            )
            
            account_strategy = AccountSelectionStrategy()
            self._token_service = AutoTokenAcquisitionService(
                auto_login_service=self.auto_login_service,
                account_selection_strategy=account_strategy,
            )
        return self._token_service
    
    def single_auto_login(
        self,
        credential_id: int,
        admin_user: str,
    ) -> LoginResult:
        """
        单个账号自动登录
        
        Args:
            credential_id: 凭证ID
            admin_user: 管理员用户名
            
        Returns:
            LoginResult: 登录结果
            
        Raises:
            NotFoundError: 凭证不存在
        """
        from ..models import AccountCredential
        
        start_time = timezone.now()
        
        # 获取凭证
        credential = AccountCredential.objects.filter(id=credential_id).first()
        if not credential:
            raise NotFoundError(f"账号凭证 #{credential_id} 不存在")
        
        # 检查是否支持自动登录
        if credential.site_name != self.SUPPORTED_SITE:
            return LoginResult(
                success=False,
                duration=0,
                error_message=f"账号 {credential.account} 不支持自动登录（仅支持法院一张网）",
            )
        
        logger.info(
            "管理员手动触发自动登录",
            extra={
                "admin_user": admin_user,
                "credential_id": credential_id,
                "account": credential.account,
                "site_name": credential.site_name,
            },
        )
        
        try:
            # 执行自动登录
            result = asyncio.run(
                self.token_service.acquire_token_if_needed(
                    site_name=self.SUPPORTED_SITE,
                    credential_id=credential.id,
                )
            )
            
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            
            if result:
                self._record_login_history(
                    credential=credential,
                    success=True,
                    duration=duration,
                    token=result,
                    trigger_reason="manual_trigger_admin",
                    start_time=start_time,
                    end_time=end_time,
                )
                
                logger.info(
                    "管理员手动登录成功",
                    extra={
                        "admin_user": admin_user,
                        "credential_id": credential_id,
                        "account": credential.account,
                        "duration": duration,
                    },
                )
                
                return LoginResult(
                    success=True,
                    duration=duration,
                    token=result,
                )
            else:
                self._record_login_history(
                    credential=credential,
                    success=False,
                    duration=duration,
                    error_message="登录失败，未返回Token",
                    trigger_reason="manual_trigger_admin",
                    start_time=start_time,
                    end_time=end_time,
                )
                
                logger.error(
                    "管理员手动登录失败",
                    extra={
                        "admin_user": admin_user,
                        "credential_id": credential_id,
                        "account": credential.account,
                        "duration": duration,
                    },
                )
                
                return LoginResult(
                    success=False,
                    duration=duration,
                    error_message="登录失败，未返回Token",
                )
                
        except Exception as e:
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            
            self._record_login_history(
                credential=credential,
                success=False,
                duration=duration,
                error_message=str(e),
                trigger_reason="manual_trigger_admin",
                start_time=start_time,
                end_time=end_time,
                error_details={
                    "error_type": type(e).__name__,
                    "admin_user": admin_user,
                    "traceback": str(e),
                },
            )
            
            logger.error(
                "管理员手动登录发生异常",
                extra={
                    "admin_user": admin_user,
                    "credential_id": credential_id,
                    "error": str(e),
                    "duration": duration,
                },
                exc_info=True,
            )
            
            return LoginResult(
                success=False,
                duration=duration,
                error_message=str(e),
            )

    def batch_auto_login(
        self,
        credential_ids: List[int],
        admin_user: str,
    ) -> BatchLoginResult:
        """
        批量自动登录
        
        Args:
            credential_ids: 凭证ID列表
            admin_user: 管理员用户名
            
        Returns:
            BatchLoginResult: 批量登录结果
        """
        from ..models import AccountCredential
        
        # 只处理法院一张网的账号
        court_credentials = AccountCredential.objects.filter(
            id__in=credential_ids,
            site_name=self.SUPPORTED_SITE,
        )
        
        if not court_credentials.exists():
            return BatchLoginResult(
                success_count=0,
                error_count=0,
                total_duration=0,
                message="没有找到法院一张网账号",
            )
        
        logger.info(
            "管理员批量触发自动登录",
            extra={
                "admin_user": admin_user,
                "credential_count": court_credentials.count(),
                "credential_ids": list(court_credentials.values_list("id", flat=True)),
            },
        )
        
        success_count = 0
        error_count = 0
        total_duration = 0.0
        
        for credential in court_credentials:
            result = self._execute_single_login(
                credential=credential,
                admin_user=admin_user,
                trigger_reason="batch_manual_trigger_admin",
            )
            
            total_duration += result.duration
            
            if result.success:
                success_count += 1
            else:
                error_count += 1
        
        # 汇总结果
        total_count = court_credentials.count()
        avg_duration = total_duration / total_count if total_count > 0 else 0
        
        logger.info(
            "批量自动登录完成",
            extra={
                "admin_user": admin_user,
                "total_credentials": total_count,
                "success_count": success_count,
                "error_count": error_count,
                "total_duration": total_duration,
                "avg_duration": avg_duration,
            },
        )
        
        # 构建消息
        messages = []
        if success_count > 0:
            messages.append(f"✅ 成功触发 {success_count} 个账号的自动登录")
        if error_count > 0:
            messages.append(f"❌ {error_count} 个账号登录失败")
        messages.append(f"总耗时 {total_duration:.1f}秒")
        
        return BatchLoginResult(
            success_count=success_count,
            error_count=error_count,
            total_duration=total_duration,
            message="，".join(messages),
        )
    
    def _execute_single_login(
        self,
        credential,
        admin_user: str,
        trigger_reason: str,
    ) -> LoginResult:
        """
        执行单个账号登录（内部方法）
        
        Args:
            credential: AccountCredential 实例
            admin_user: 管理员用户名
            trigger_reason: 触发原因
            
        Returns:
            LoginResult: 登录结果
        """
        start_time = timezone.now()
        
        try:
            result = asyncio.run(
                self.token_service.acquire_token_if_needed(
                    site_name=self.SUPPORTED_SITE,
                    credential_id=credential.id,
                )
            )
            
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            
            if result:
                self._record_login_history(
                    credential=credential,
                    success=True,
                    duration=duration,
                    token=result,
                    trigger_reason=trigger_reason,
                    start_time=start_time,
                    end_time=end_time,
                )
                
                logger.info(
                    "批量登录成功",
                    extra={
                        "admin_user": admin_user,
                        "credential_id": credential.id,
                        "account": credential.account,
                        "duration": duration,
                    },
                )
                
                return LoginResult(success=True, duration=duration, token=result)
            else:
                self._record_login_history(
                    credential=credential,
                    success=False,
                    duration=duration,
                    error_message="登录失败，未返回Token",
                    trigger_reason=trigger_reason,
                    start_time=start_time,
                    end_time=end_time,
                )
                
                return LoginResult(
                    success=False,
                    duration=duration,
                    error_message="登录失败，未返回Token",
                )
                
        except Exception as e:
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            
            self._record_login_history(
                credential=credential,
                success=False,
                duration=duration,
                error_message=str(e),
                trigger_reason=trigger_reason,
                start_time=start_time,
                end_time=end_time,
                error_details={
                    "error_type": type(e).__name__,
                    "admin_user": admin_user,
                    "batch_operation": True,
                },
            )
            
            logger.error(
                "批量登录失败",
                extra={
                    "admin_user": admin_user,
                    "credential_id": credential.id,
                    "account": credential.account,
                    "error": str(e),
                    "duration": duration,
                },
                exc_info=True,
            )
            
            return LoginResult(success=False, duration=duration, error_message=str(e))

    def _record_login_history(
        self,
        credential,
        success: bool,
        duration: float,
        trigger_reason: str,
        start_time,
        end_time,
        token: Optional[str] = None,
        error_message: Optional[str] = None,
        error_details: Optional[dict] = None,
    ) -> None:
        """
        记录登录历史
        
        Args:
            credential: AccountCredential 实例
            success: 是否成功
            duration: 耗时（秒）
            trigger_reason: 触发原因
            start_time: 开始时间
            end_time: 结束时间
            token: Token（成功时）
            error_message: 错误消息（失败时）
            error_details: 错误详情（失败时）
        """
        # 通过ServiceLocator获取automation服务
        from apps.core.interfaces import ServiceLocator
        
        try:
            automation_service = ServiceLocator.get_automation_service()
            
            # 构建历史记录数据
            history_data = {
                "site_name": credential.site_name,
                "account": credential.account,
                "credential_id": credential.id,
                "trigger_reason": trigger_reason,
                "attempt_count": 1,
                "total_duration": duration,
                "created_at": start_time,
                "started_at": start_time,
                "finished_at": end_time,
            }
            
            if success:
                history_data.update({
                    "status": "SUCCESS",
                    "token_preview": token[:50] if token and len(token) > 50 else token,
                })
            else:
                history_data.update({
                    "status": "FAILED",
                    "error_message": error_message,
                    "error_details": error_details,
                })
            
            # 通过automation服务创建历史记录
            automation_service.create_token_acquisition_history_internal(history_data)
            
        except Exception as e:
            # 记录历史失败不影响主流程
            logger.warning(
                "记录登录历史失败",
                extra={
                    "credential_id": credential.id,
                    "error": str(e),
                },
            )
