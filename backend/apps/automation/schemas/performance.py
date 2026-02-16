"""性能监控 Schemas"""

from typing import Any

from pydantic import BaseModel, Field


class PerformanceMetricsOut(BaseModel):
    """性能指标输出Schema"""

    total_acquisitions: int = Field(..., description="总获取次数")
    successful_acquisitions: int = Field(..., description="成功获取次数")
    failed_acquisitions: int = Field(..., description="失败获取次数")
    success_rate: float = Field(..., description="成功率(百分比)")
    avg_duration: float = Field(..., description="平均耗时(秒)")
    avg_login_duration: float = Field(..., description="平均登录耗时(秒)")
    timeout_count: int = Field(..., description="超时次数")
    network_error_count: int = Field(..., description="网络错误次数")
    captcha_error_count: int = Field(..., description="验证码错误次数")
    credential_error_count: int = Field(..., description="凭证错误次数")
    concurrent_acquisitions: int = Field(..., description="当前并发获取数")
    cache_hit_rate: float = Field(..., description="缓存命中率(百分比)")


class StatisticsReportOut(BaseModel):
    """统计报告输出Schema"""

    period: dict[str, Any] = Field(..., description="统计周期信息")
    summary: dict[str, Any] = Field(..., description="汇总统计")
    status_breakdown: list[dict[str, Any]] = Field(..., description="按状态分组统计")
    site_breakdown: list[dict[str, Any]] = Field(..., description="按网站分组统计")
    account_breakdown: list[dict[str, Any]] = Field(..., description="按账号分组统计")
    daily_trend: list[dict[str, Any]] = Field(..., description="每日趋势")
    real_time_metrics: dict[str, Any] = Field(..., description="实时指标")


class AlertSchema(BaseModel):
    """告警信息Schema"""

    type: str = Field(..., description="告警类型")
    message: str = Field(..., description="告警消息")
    severity: str = Field(..., description="严重程度")


class HealthCheckOut(BaseModel):
    """健康检查输出Schema"""

    status: str = Field(..., description="健康状态")
    timestamp: str = Field(..., description="检查时间")
    metrics: dict[str, Any] = Field(..., description="性能指标")
    alerts: list[AlertSchema] = Field(..., description="告警列表")
    thresholds: dict[str, Any] = Field(..., description="告警阈值")


class ResourceUsageOut(BaseModel):
    """资源使用情况输出Schema"""

    total_acquisitions: int = Field(..., description="总并发获取数")
    site_acquisitions: dict[str, Any] = Field(..., description="按网站分组的并发数")
    account_acquisitions: dict[str, Any] = Field(..., description="按账号分组的并发数")
    active_locks: int = Field(..., description="活跃锁数量")
    queue_size: int = Field(..., description="队列大小")
    config: dict[str, Any] = Field(..., description="并发配置")
