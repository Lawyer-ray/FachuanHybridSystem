# 自动Token获取功能集成指南

## 概述

本文档描述财产保险询价服务与自动Token获取功能的集成实现。该集成使得询价任务能够在Token无效时自动获取新Token，无需人工干预。

## 架构设计

```
API层 (preservation_quote_api.py)
    ↓ 使用工厂函数
服务适配器 (PreservationQuoteServiceAdapter)
    ↓ 创建并注入依赖
增强版服务 (EnhancedPreservationQuoteService)
    ↓ 继承并增强
原始服务 (PreservationQuoteService)
    ↓ 集成自动Token获取
自动Token获取服务 (AutoTokenAcquisitionService)
```

## 核心组件

### 1. API层工厂函数

```python
def _get_preservation_quote_service() -> PreservationQuoteServiceAdapter:
    """工厂函数：创建服务实例并注入依赖"""
    from apps.automation.services.scraper.core.token_service import TokenService
    from apps.automation.services.insurance.court_insurance_client import CourtInsuranceClient
    from apps.core.interfaces import ServiceLocator
    
    return PreservationQuoteServiceAdapter(
        token_service=TokenService(),
        insurance_client=CourtInsuranceClient(),
        auto_token_service=ServiceLocator.get_auto_token_acquisition_service()
    )
```

### 2. ServiceLocator扩展

```python
@classmethod
def get_auto_token_acquisition_service(cls) -> IAutoTokenAcquisitionService:
    """获取自动Token获取服务"""
    service = cls.get("auto_token_acquisition_service")
    if service is None:
        from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
        service = AutoTokenAcquisitionService()
        cls.register("auto_token_acquisition_service", service)
    return service
```

### 3. 增强版服务

```python
class EnhancedPreservationQuoteService(PreservationQuoteService):
    """增强版服务，集成自动Token获取功能"""
    
    async def _get_valid_token(self, site_name: str, credential_id: Optional[int] = None) -> str:
        """获取有效Token（重写父类方法）"""
        return await self.auto_token_service.acquire_token_if_needed(site_name, credential_id)
```

## 使用示例

### 基本使用

```python
service = _get_preservation_quote_service()
result = await service.execute_quote(quote_id)
```

### 测试时注入Mock

```python
mock_service = Mock(spec=IAutoTokenAcquisitionService)
ServiceLocator.register("auto_token_acquisition_service", mock_service)
service = _get_preservation_quote_service()
# service.auto_token_service 现在是Mock对象
```

## 功能特性

- **自动Token获取**: Token无效时自动触发登录流程
- **账号选择**: 支持指定凭证ID或自动选择最优账号
- **并发控制**: 避免多个任务同时触发登录
- **缓存机制**: 复用有效Token，减少登录频率
- **完整日志**: 执行轨迹和性能监控

## 测试

```bash
pytest tests/unit/automation/test_preservation_quote_factory.py -v
pytest tests/integration/automation/test_preservation_quote_auto_token_integration.py -v
```

## 故障排除

1. **Token获取失败**: 检查账号凭证、网络连接、错误日志
2. **登录超时**: 检查网络延迟、调整超时配置
3. **并发冲突**: 系统自动处理，查看并发统计日志
