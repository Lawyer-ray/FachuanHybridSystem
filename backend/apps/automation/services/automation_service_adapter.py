"""
自动化服务适配器

提供自动化模块对外的统一服务接口
"""
import logging
from typing import Dict, Any
from django.utils import timezone

from apps.core.interfaces import IAutomationService
from apps.automation.models import TokenAcquisitionHistory, TokenAcquisitionStatus
from apps.core.exceptions import ValidationError

logger = logging.getLogger("apps.automation")


class AutomationServiceAdapter(IAutomationService):
    """
    自动化服务适配器
    
    实现IAutomationService接口，提供自动化模块的核心功能
    """
    
    def create_token_acquisition_history_internal(self, history_data: Dict[str, Any]) -> TokenAcquisitionHistory:
        """
        创建Token获取历史记录（内部方法）
        
        Args:
            history_data: 历史记录数据
            
        Returns:
            创建的历史记录对象
            
        Raises:
            ValidationError: 数据验证失败
        """
        logger.info(
            "创建Token获取历史记录",
            extra={
                "action": "create_token_acquisition_history_internal",
                "site_name": history_data.get("site_name"),
                "account": history_data.get("account"),
                "status": history_data.get("status"),
            }
        )
        
        try:
            # 数据验证
            required_fields = ["site_name", "account", "credential_id", "status", "trigger_reason"]
            for field in required_fields:
                if field not in history_data:
                    raise ValidationError(
                        message=f"缺少必需字段: {field}",
                        code="MISSING_REQUIRED_FIELD",
                        errors={field: "此字段为必需"}
                    )
            
            # 状态转换
            status_mapping = {
                "SUCCESS": TokenAcquisitionStatus.SUCCESS,
                "FAILED": TokenAcquisitionStatus.FAILED,
            }
            
            status = status_mapping.get(history_data["status"])
            if status is None:
                raise ValidationError(
                    message=f"无效的状态值: {history_data['status']}",
                    code="INVALID_STATUS",
                    errors={"status": f"状态必须是 {list(status_mapping.keys())} 之一"}
                )
            
            # 创建历史记录
            history = TokenAcquisitionHistory.objects.create(
                site_name=history_data["site_name"],
                account=history_data["account"],
                credential_id=history_data["credential_id"],
                status=status,
                trigger_reason=history_data["trigger_reason"],
                attempt_count=history_data.get("attempt_count", 1),
                total_duration=history_data.get("total_duration", 0.0),
                token_preview=history_data.get("token_preview"),
                error_message=history_data.get("error_message"),
                error_details=history_data.get("error_details"),
                created_at=history_data.get("created_at", timezone.now()),
                started_at=history_data.get("started_at", timezone.now()),
                finished_at=history_data.get("finished_at", timezone.now()),
            )
            
            logger.info(
                "✅ Token获取历史记录创建成功",
                extra={
                    "action": "create_token_acquisition_history_success",
                    "history_id": history.id,
                    "site_name": history.site_name,
                    "account": history.account,
                    "status": history.status,
                }
            )
            
            return history
            
        except ValidationError:
            # 重新抛出验证错误
            raise
        except Exception as e:
            logger.error(
                f"❌ 创建Token获取历史记录失败: {e}",
                extra={
                    "action": "create_token_acquisition_history_failed",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "history_data": history_data,
                },
                exc_info=True
            )
            raise ValidationError(
                message=f"创建Token获取历史记录失败: {str(e)}",
                code="CREATE_HISTORY_FAILED",
                errors={"internal_error": str(e)}
            )