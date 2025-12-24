# 自动Token获取功能示例代码

## 概述

本文档提供了自动Token获取功能的完整示例代码，展示如何在不同场景下集成和使用该功能。

## 基础使用示例

### 1. 简单的Token获取

```python
# examples/basic_token_acquisition.py

import asyncio
import logging
from apps.core.interfaces import ServiceLocator
from apps.core.exceptions import AutoTokenAcquisitionError

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def basic_token_example():
    """基础Token获取示例"""
    try:
        # 获取自动Token服务
        service = ServiceLocator.get_auto_token_acquisition_service()
        
        # 自动获取Token（自动选择账号）
        token = await service.acquire_token_if_needed("court_zxfw")
        logger.info(f"成功获取Token: {token[:10]}...")
        
        return token
        
    except AutoTokenAcquisitionError as e:
        logger.error(f"Token获取失败: {e.message}")
        raise

# 运行示例
if __name__ == "__main__":
    asyncio.run(basic_token_example())
```

### 2. 指定凭证ID获取Token

```python
# examples/credential_specific_token.py

import asyncio
from apps.core.interfaces import ServiceLocator
from apps.core.exceptions import ValidationException, NoAvailableAccountError

async def credential_specific_example():
    """使用指定凭证获取Token示例"""
    service = ServiceLocator.get_auto_token_acquisition_service()
    
    try:
        # 使用指定的凭证ID获取Token
        credential_id = 1
        token = await service.acquire_token_if_needed("court_zxfw", credential_id)
        print(f"使用凭证ID {credential_id} 获取Token成功: {token[:10]}...")
        
    except ValidationException as e:
        print(f"参数验证失败: {e.message}")
    except NoAvailableAccountError:
        print("指定的凭证不存在或不可用")
    except AutoTokenAcquisitionError as e:
        print(f"Token获取失败: {e.message}")

asyncio.run(credential_specific_example())
```

## 服务集成示例

### 3. 在业务服务中集成

```python
# examples/business_service_integration.py

from typing import Optional, Dict, Any
from apps.core.interfaces import IAutoTokenAcquisitionService, ServiceLocator
from apps.core.exceptions import AutoTokenAcquisitionError, BusinessException
import logging

logger = logging.getLogger(__name__)

class DocumentService:
    """文档服务示例 - 集成自动Token获取"""
    
    def __init__(self, auto_token_service: Optional[IAutoTokenAcquisitionService] = None):
        self._auto_token_service = auto_token_service
    
    @property
    def auto_token_service(self) -> IAutoTokenAcquisitionService:
        """获取自动Token服务（延迟加载）"""
        if self._auto_token_service is None:
            self._auto_token_service = ServiceLocator.get_auto_token_acquisition_service()
        return self._auto_token_service
    
    async def download_document(self, document_id: str, credential_id: Optional[int] = None) -> Dict[str, Any]:
        """
        下载文档示例
        
        Args:
            document_id: 文档ID
            credential_id: 指定的凭证ID（可选）
            
        Returns:
            下载结果
        """
        try:
            logger.info(f"开始下载文档: {document_id}")
            
            # 自动获取Token
            token = await self.auto_token_service.acquire_token_if_needed(
                "court_zxfw", credential_id
            )
            
            # 使用Token下载文档
            result = await self._download_with_token(document_id, token)
            
            logger.info(f"文档下载成功: {document_id}")
            return result
            
        except AutoTokenAcquisitionError as e:
            logger.error(f"Token获取失败，无法下载文档: {e.message}")
            raise BusinessException("文档下载失败，请稍后重试")
        except Exception as e:
            logger.error(f"文档下载过程中发生错误: {e}")
            raise BusinessException("文档下载失败")
    
    async def _download_with_token(self, document_id: str, token: str) -> Dict[str, Any]:
        """使用Token下载文档的具体实现"""
        # 模拟下载逻辑
        import asyncio
        await asyncio.sleep(1)  # 模拟网络请求
        
        return {
            "document_id": document_id,
            "status": "success",
            "file_size": 1024,
            "download_url": f"https://example.com/download/{document_id}"
        }

# 使用示例
async def document_service_example():
    """文档服务使用示例"""
    service = DocumentService()
    
    try:
        # 下载文档（自动选择账号）
        result = await service.download_document("DOC123")
        print(f"下载结果: {result}")
        
        # 下载文档（指定凭证）
        result = await service.download_document("DOC456", credential_id=1)
        print(f"下载结果: {result}")
        
    except BusinessException as e:
        print(f"业务异常: {e.message}")

# 运行示例
import asyncio
asyncio.run(document_service_example())
```

### 4. 服务适配器模式

```python
# examples/service_adapter_pattern.py

from typing import Optional
from apps.core.interfaces import IAutoTokenAcquisitionService, ServiceLocator

class LegacyQuoteService:
    """遗留的询价服务（不支持自动Token获取）"""
    
    def __init__(self, token_service):
        self.token_service = token_service
    
    async def execute_quote(self, quote_id: int, token: str) -> Dict[str, Any]:
        """执行询价（需要手动传入Token）"""
        # 模拟询价逻辑
        return {
            "quote_id": quote_id,
            "status": "completed",
            "companies_count": 5,
            "success_count": 4
        }

class EnhancedQuoteService(LegacyQuoteService):
    """增强版询价服务（支持自动Token获取）"""
    
    def __init__(self, token_service, auto_token_service: Optional[IAutoTokenAcquisitionService] = None):
        super().__init__(token_service)
        self._auto_token_service = auto_token_service
    
    @property
    def auto_token_service(self) -> IAutoTokenAcquisitionService:
        """获取自动Token服务（延迟加载）"""
        if self._auto_token_service is None:
            self._auto_token_service = ServiceLocator.get_auto_token_acquisition_service()
        return self._auto_token_service
    
    async def execute_quote_auto(self, quote_id: int, credential_id: Optional[int] = None) -> Dict[str, Any]:
        """执行询价（自动获取Token）"""
        try:
            # 自动获取Token
            token = await self.auto_token_service.acquire_token_if_needed(
                "court_zxfw", credential_id
            )
            
            # 调用父类方法执行询价
            return await super().execute_quote(quote_id, token)
            
        except AutoTokenAcquisitionError as e:
            logger.error(f"询价执行失败，Token获取失败: {e.message}")
            raise BusinessException("询价服务暂时不可用")

class QuoteServiceAdapter:
    """询价服务适配器"""
    
    def __init__(self, auto_token_service: Optional[IAutoTokenAcquisitionService] = None):
        self._auto_token_service = auto_token_service
        self._service = None
    
    @property
    def service(self) -> EnhancedQuoteService:
        """获取增强版服务（延迟加载）"""
        if self._service is None:
            from apps.automation.services.scraper.core.token_service import TokenService
            token_service = TokenService()
            
            self._service = EnhancedQuoteService(
                token_service=token_service,
                auto_token_service=self._auto_token_service
            )
        return self._service
    
    async def execute_quote(self, quote_id: int, credential_id: Optional[int] = None) -> Dict[str, Any]:
        """执行询价（代理到增强版服务）"""
        return await self.service.execute_quote_auto(quote_id, credential_id)

# 使用示例
async def adapter_pattern_example():
    """适配器模式使用示例"""
    # 创建适配器
    adapter = QuoteServiceAdapter()
    
    try:
        # 执行询价
        result = await adapter.execute_quote(123)
        print(f"询价结果: {result}")
        
    except BusinessException as e:
        print(f"询价失败: {e.message}")

asyncio.run(adapter_pattern_example())
```

## API集成示例

### 5. Django Ninja API集成

```python
# examples/api_integration.py

from ninja import Router, Schema
from ninja_jwt.authentication import JWTAuth
from django.http import HttpRequest
from typing import Optional
from apps.core.interfaces import ServiceLocator
from apps.core.exceptions import AutoTokenAcquisitionError, BusinessException

# 请求和响应Schema
class DocumentDownloadRequest(Schema):
    document_id: str
    credential_id: Optional[int] = None

class DocumentDownloadResponse(Schema):
    success: bool
    message: str
    data: Optional[dict] = None

# 创建路由器
router = Router(tags=["文档管理"], auth=JWTAuth())

def _get_document_service():
    """工厂函数：创建文档服务实例"""
    auto_token_service = ServiceLocator.get_auto_token_acquisition_service()
    return DocumentService(auto_token_service=auto_token_service)

@router.post("/documents/download", response=DocumentDownloadResponse)
async def download_document(request: HttpRequest, data: DocumentDownloadRequest):
    """
    下载文档API
    
    自动处理Token获取和文档下载
    """
    try:
        # 创建服务实例
        service = _get_document_service()
        
        # 执行下载
        result = await service.download_document(
            document_id=data.document_id,
            credential_id=data.credential_id
        )
        
        return DocumentDownloadResponse(
            success=True,
            message="文档下载成功",
            data=result
        )
        
    except BusinessException as e:
        return DocumentDownloadResponse(
            success=False,
            message=e.message
        )
    except Exception as e:
        logger.error(f"API执行失败: {e}")
        return DocumentDownloadResponse(
            success=False,
            message="服务器内部错误"
        )

@router.get("/documents/token-status")
async def get_token_status(request: HttpRequest, site_name: str = "court_zxfw"):
    """
    获取Token状态API
    
    检查指定站点的Token状态
    """
    try:
        service = ServiceLocator.get_auto_token_acquisition_service()
        
        # 尝试获取Token（不会触发登录，只检查现有Token）
        from apps.automation.services.token.cache_manager import cache_manager
        
        # 检查缓存中的Token
        cached_tokens = cache_manager.get_site_tokens(site_name)
        
        return {
            "success": True,
            "site_name": site_name,
            "cached_tokens_count": len(cached_tokens),
            "tokens": [
                {
                    "account": account,
                    "token_length": len(token),
                    "cached_at": "unknown"  # 实际实现中可以添加时间戳
                }
                for account, token in cached_tokens.items()
            ]
        }
        
    except Exception as e:
        logger.error(f"获取Token状态失败: {e}")
        return {
            "success": False,
            "message": "获取Token状态失败"
        }
```

## 错误处理示例

### 6. 完整的错误处理

```python
# examples/error_handling.py

import asyncio
import logging
from typing import Optional, Dict, Any
from apps.core.interfaces import ServiceLocator
from apps.core.exceptions import (
    AutoTokenAcquisitionError,
    LoginFailedError,
    NoAvailableAccountError,
    TokenAcquisitionTimeoutError,
    ValidationException
)

logger = logging.getLogger(__name__)

class RobustTokenService:
    """健壮的Token服务示例"""
    
    def __init__(self):
        self.auto_token_service = ServiceLocator.get_auto_token_acquisition_service()
    
    async def get_token_with_fallback(
        self, 
        site_name: str, 
        preferred_credential_id: Optional[int] = None
    ) -> Optional[str]:
        """
        带降级策略的Token获取
        
        Args:
            site_name: 网站名称
            preferred_credential_id: 首选凭证ID
            
        Returns:
            Token字符串，如果所有方式都失败则返回None
        """
        strategies = [
            ("指定凭证", preferred_credential_id),
            ("自动选择", None)
        ]
        
        for strategy_name, credential_id in strategies:
            if credential_id is None and strategy_name == "指定凭证":
                continue  # 跳过无效的指定凭证策略
                
            try:
                logger.info(f"尝试使用{strategy_name}策略获取Token")
                
                token = await self.auto_token_service.acquire_token_if_needed(
                    site_name, credential_id
                )
                
                logger.info(f"使用{strategy_name}策略获取Token成功")
                return token
                
            except ValidationException as e:
                logger.warning(f"{strategy_name}策略参数验证失败: {e.message}")
                continue
                
            except NoAvailableAccountError:
                logger.warning(f"{strategy_name}策略无可用账号")
                continue
                
            except LoginFailedError as e:
                logger.warning(f"{strategy_name}策略登录失败: {e.message}")
                if e.attempts:
                    logger.info(f"登录尝试详情: {len(e.attempts)}次尝试")
                continue
                
            except TokenAcquisitionTimeoutError:
                logger.warning(f"{strategy_name}策略获取超时")
                continue
                
            except AutoTokenAcquisitionError as e:
                logger.error(f"{strategy_name}策略获取失败: {e.message}")
                continue
        
        logger.error("所有Token获取策略都失败")
        return None
    
    async def execute_with_retry(
        self, 
        operation_func, 
        site_name: str, 
        max_retries: int = 3,
        *args, 
        **kwargs
    ) -> Any:
        """
        带重试的操作执行
        
        Args:
            operation_func: 要执行的操作函数
            site_name: 网站名称
            max_retries: 最大重试次数
            *args, **kwargs: 传递给操作函数的参数
            
        Returns:
            操作结果
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                # 获取Token
                token = await self.get_token_with_fallback(site_name)
                if not token:
                    raise AutoTokenAcquisitionError("无法获取有效Token")
                
                # 执行操作
                result = await operation_func(token, *args, **kwargs)
                
                logger.info(f"操作执行成功 (尝试 {attempt + 1})")
                return result
                
            except Exception as e:
                last_exception = e
                logger.warning(f"操作执行失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                
                if attempt < max_retries:
                    # 等待后重试
                    wait_time = 2 ** attempt  # 指数退避
                    logger.info(f"等待 {wait_time} 秒后重试")
                    await asyncio.sleep(wait_time)
        
        # 所有重试都失败
        logger.error(f"操作最终失败，已重试 {max_retries} 次")
        raise last_exception

# 使用示例
async def robust_operation_example():
    """健壮操作示例"""
    service = RobustTokenService()
    
    async def mock_business_operation(token: str, data: str) -> Dict[str, Any]:
        """模拟业务操作"""
        # 模拟可能失败的操作
        import random
        if random.random() < 0.3:  # 30%的失败率
            raise Exception("模拟业务操作失败")
        
        return {
            "status": "success",
            "data": data,
            "token_used": token[:10] + "..."
        }
    
    try:
        # 执行带重试的操作
        result = await service.execute_with_retry(
            mock_business_operation,
            "court_zxfw",
            max_retries=2,
            data="test_data"
        )
        
        print(f"操作成功: {result}")
        
    except Exception as e:
        print(f"操作最终失败: {e}")

asyncio.run(robust_operation_example())
```

## 性能优化示例

### 7. 缓存和性能优化

```python
# examples/performance_optimization.py

import asyncio
import time
from typing import Dict, Optional, Tuple
from apps.core.interfaces import ServiceLocator
from apps.automation.services.token.cache_manager import cache_manager
from apps.automation.services.token.performance_monitor import performance_monitor

class OptimizedTokenService:
    """性能优化的Token服务"""
    
    def __init__(self):
        self.auto_token_service = ServiceLocator.get_auto_token_acquisition_service()
        self._local_cache: Dict[str, Tuple[str, float]] = {}
        self._cache_ttl = 300  # 5分钟本地缓存
    
    async def get_token_optimized(self, site_name: str, credential_id: Optional[int] = None) -> str:
        """
        优化的Token获取
        
        多级缓存策略：
        1. 本地内存缓存
        2. Redis缓存
        3. 自动获取
        """
        cache_key = f"{site_name}_{credential_id or 'auto'}"
        
        # 1. 检查本地缓存
        if cache_key in self._local_cache:
            token, timestamp = self._local_cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"本地缓存命中: {cache_key}")
                return token
            else:
                # 缓存过期，删除
                del self._local_cache[cache_key]
        
        # 2. 检查Redis缓存
        if credential_id:
            # 对于指定凭证，需要先获取账号信息
            from apps.organization.models import AccountCredential
            try:
                credential = await asyncio.get_event_loop().run_in_executor(
                    None, AccountCredential.objects.get, credential_id
                )
                cached_token = cache_manager.get_cached_token(site_name, credential.account)
                if cached_token:
                    logger.debug(f"Redis缓存命中: {site_name}_{credential.account}")
                    # 更新本地缓存
                    self._local_cache[cache_key] = (cached_token, time.time())
                    return cached_token
            except AccountCredential.DoesNotExist:
                pass
        
        # 3. 自动获取Token
        logger.debug(f"缓存未命中，自动获取Token: {cache_key}")
        token = await self.auto_token_service.acquire_token_if_needed(site_name, credential_id)
        
        # 更新本地缓存
        self._local_cache[cache_key] = (token, time.time())
        
        return token
    
    async def batch_get_tokens(self, requests: List[Tuple[str, Optional[int]]]) -> Dict[str, str]:
        """
        批量获取Token
        
        Args:
            requests: (site_name, credential_id) 的列表
            
        Returns:
            {cache_key: token} 的字典
        """
        results = {}
        
        # 并发获取所有Token
        tasks = []
        for site_name, credential_id in requests:
            cache_key = f"{site_name}_{credential_id or 'auto'}"
            task = asyncio.create_task(
                self.get_token_optimized(site_name, credential_id),
                name=cache_key
            )
            tasks.append((cache_key, task))
        
        # 等待所有任务完成
        for cache_key, task in tasks:
            try:
                token = await task
                results[cache_key] = token
            except Exception as e:
                logger.error(f"批量获取Token失败 {cache_key}: {e}")
                results[cache_key] = None
        
        return results
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "local_cache_size": len(self._local_cache),
            "local_cache_keys": list(self._local_cache.keys()),
            "redis_cache_stats": cache_manager.get_cache_stats(),
            "performance_metrics": performance_monitor.get_metrics()
        }
    
    def clear_local_cache(self):
        """清除本地缓存"""
        self._local_cache.clear()
        logger.info("本地缓存已清除")

# 使用示例
async def performance_optimization_example():
    """性能优化示例"""
    service = OptimizedTokenService()
    
    # 单个Token获取
    start_time = time.time()
    token1 = await service.get_token_optimized("court_zxfw")
    duration1 = time.time() - start_time
    print(f"首次获取耗时: {duration1:.2f}秒")
    
    # 再次获取（应该命中缓存）
    start_time = time.time()
    token2 = await service.get_token_optimized("court_zxfw")
    duration2 = time.time() - start_time
    print(f"缓存获取耗时: {duration2:.2f}秒")
    
    assert token1 == token2
    print(f"缓存加速比: {duration1/duration2:.1f}x")
    
    # 批量获取Token
    requests = [
        ("court_zxfw", None),
        ("court_zxfw", 1),
        ("other_site", None)
    ]
    
    start_time = time.time()
    batch_results = await service.batch_get_tokens(requests)
    batch_duration = time.time() - start_time
    
    print(f"批量获取 {len(requests)} 个Token耗时: {batch_duration:.2f}秒")
    print(f"批量获取结果: {batch_results}")
    
    # 获取缓存统计
    stats = service.get_cache_stats()
    print(f"缓存统计: {stats}")

asyncio.run(performance_optimization_example())
```

## 监控和调试示例

### 8. 监控和调试工具

```python
# examples/monitoring_debugging.py

import asyncio
import json
from datetime import datetime, timedelta
from apps.automation.services.token.performance_monitor import performance_monitor
from apps.automation.services.token.cache_manager import cache_manager
from apps.automation.services.token.history_recorder import history_recorder

class TokenMonitoringService:
    """Token监控服务"""
    
    def __init__(self):
        self.performance_monitor = performance_monitor
        self.cache_manager = cache_manager
        self.history_recorder = history_recorder
    
    async def get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        try:
            # 获取性能指标
            metrics = self.performance_monitor.get_metrics()
            
            # 获取缓存统计
            cache_stats = self.cache_manager.get_cache_stats()
            
            # 获取历史统计
            history_stats = await self._get_history_stats()
            
            # 计算健康分数
            health_score = self._calculate_health_score(metrics, cache_stats)
            
            return {
                "timestamp": datetime.now().isoformat(),
                "health_score": health_score,
                "status": self._get_health_status(health_score),
                "metrics": metrics,
                "cache_stats": cache_stats,
                "history_stats": history_stats,
                "recommendations": self._get_recommendations(metrics, cache_stats)
            }
            
        except Exception as e:
            logger.error(f"获取系统健康状态失败: {e}")
            return {
                "timestamp": datetime.now().isoformat(),
                "health_score": 0,
                "status": "error",
                "error": str(e)
            }
    
    def _calculate_health_score(self, metrics: Dict, cache_stats: Dict) -> float:
        """计算健康分数（0-100）"""
        score = 100.0
        
        # 成功率影响（权重40%）
        success_rate = metrics.get("success_rate", 0)
        score -= (100 - success_rate) * 0.4
        
        # 平均耗时影响（权重30%）
        avg_duration = metrics.get("avg_duration", 0)
        if avg_duration > 60:  # 超过60秒扣分
            score -= min((avg_duration - 60) / 60 * 30, 30)
        
        # 缓存命中率影响（权重20%）
        cache_hit_rate = cache_stats.get("hit_rate", 0)
        score -= (100 - cache_hit_rate) * 0.2
        
        # 并发数影响（权重10%）
        concurrent_count = metrics.get("concurrent_acquisitions", 0)
        if concurrent_count > 5:  # 超过5个并发扣分
            score -= min((concurrent_count - 5) * 2, 10)
        
        return max(0, score)
    
    def _get_health_status(self, score: float) -> str:
        """根据分数获取健康状态"""
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "good"
        elif score >= 60:
            return "fair"
        elif score >= 40:
            return "poor"
        else:
            return "critical"
    
    def _get_recommendations(self, metrics: Dict, cache_stats: Dict) -> List[str]:
        """获取优化建议"""
        recommendations = []
        
        success_rate = metrics.get("success_rate", 0)
        if success_rate < 80:
            recommendations.append("成功率较低，建议检查账号配置和网络状况")
        
        avg_duration = metrics.get("avg_duration", 0)
        if avg_duration > 120:
            recommendations.append("平均耗时过长，建议优化网络配置或增加并发数")
        
        cache_hit_rate = cache_stats.get("hit_rate", 0)
        if cache_hit_rate < 70:
            recommendations.append("缓存命中率较低，建议预热缓存或调整缓存策略")
        
        concurrent_count = metrics.get("concurrent_acquisitions", 0)
        if concurrent_count > 8:
            recommendations.append("并发数过高，可能影响系统性能")
        
        return recommendations
    
    async def _get_history_stats(self) -> Dict[str, Any]:
        """获取历史统计"""
        try:
            # 获取最近24小时的统计
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)
            
            # 这里应该调用实际的历史记录查询方法
            # 由于示例中没有具体实现，这里返回模拟数据
            return {
                "last_24h_acquisitions": 150,
                "last_24h_success_rate": 85.5,
                "last_24h_avg_duration": 45.2,
                "peak_hour": "14:00-15:00",
                "peak_acquisitions": 25
            }
            
        except Exception as e:
            logger.error(f"获取历史统计失败: {e}")
            return {}
    
    async def run_diagnostics(self) -> Dict[str, Any]:
        """运行诊断检查"""
        diagnostics = {
            "timestamp": datetime.now().isoformat(),
            "checks": {}
        }
        
        # 检查服务可用性
        try:
            from apps.core.interfaces import ServiceLocator
            service = ServiceLocator.get_auto_token_acquisition_service()
            diagnostics["checks"]["service_availability"] = {
                "status": "pass",
                "message": "自动Token服务可用"
            }
        except Exception as e:
            diagnostics["checks"]["service_availability"] = {
                "status": "fail",
                "message": f"服务不可用: {e}"
            }
        
        # 检查缓存连接
        try:
            cache_stats = self.cache_manager.get_cache_stats()
            diagnostics["checks"]["cache_connection"] = {
                "status": "pass",
                "message": "缓存连接正常",
                "details": cache_stats
            }
        except Exception as e:
            diagnostics["checks"]["cache_connection"] = {
                "status": "fail",
                "message": f"缓存连接失败: {e}"
            }
        
        # 检查账号配置
        try:
            from apps.organization.models import AccountCredential
            account_count = await asyncio.get_event_loop().run_in_executor(
                None, AccountCredential.objects.filter(site_name="court_zxfw").count
            )
            
            if account_count > 0:
                diagnostics["checks"]["account_configuration"] = {
                    "status": "pass",
                    "message": f"找到 {account_count} 个账号配置"
                }
            else:
                diagnostics["checks"]["account_configuration"] = {
                    "status": "fail",
                    "message": "未找到账号配置"
                }
        except Exception as e:
            diagnostics["checks"]["account_configuration"] = {
                "status": "error",
                "message": f"检查账号配置失败: {e}"
            }
        
        return diagnostics

# 使用示例
async def monitoring_example():
    """监控示例"""
    monitor = TokenMonitoringService()
    
    # 获取系统健康状态
    health = await monitor.get_system_health()
    print("=== 系统健康状态 ===")
    print(json.dumps(health, indent=2, ensure_ascii=False))
    
    # 运行诊断
    diagnostics = await monitor.run_diagnostics()
    print("\n=== 诊断结果 ===")
    print(json.dumps(diagnostics, indent=2, ensure_ascii=False))
    
    # 性能监控
    print("\n=== 性能指标 ===")
    metrics = performance_monitor.get_metrics()
    for key, value in metrics.items():
        print(f"{key}: {value}")

asyncio.run(monitoring_example())
```

## 测试示例

### 9. 完整的测试示例

```python
# examples/testing_examples.py

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from apps.core.interfaces import IAutoTokenAcquisitionService, ServiceLocator
from apps.core.exceptions import AutoTokenAcquisitionError, NoAvailableAccountError

class TestAutoTokenIntegration:
    """自动Token集成测试示例"""
    
    def setup_method(self):
        """每个测试前的设置"""
        # 清理ServiceLocator
        ServiceLocator.clear()
        
        # 创建Mock服务
        self.mock_auto_token_service = Mock(spec=IAutoTokenAcquisitionService)
        
        # 注入Mock服务
        ServiceLocator.register("auto_token_acquisition_service", self.mock_auto_token_service)
    
    def teardown_method(self):
        """每个测试后的清理"""
        ServiceLocator.clear()
    
    @pytest.mark.asyncio
    async def test_successful_token_acquisition(self):
        """测试成功获取Token"""
        # 配置Mock返回值
        expected_token = "test_token_12345"
        self.mock_auto_token_service.acquire_token_if_needed.return_value = expected_token
        
        # 获取服务并测试
        service = ServiceLocator.get_auto_token_acquisition_service()
        token = await service.acquire_token_if_needed("court_zxfw")
        
        # 验证结果
        assert token == expected_token
        self.mock_auto_token_service.acquire_token_if_needed.assert_called_once_with("court_zxfw")
    
    @pytest.mark.asyncio
    async def test_token_acquisition_with_credential_id(self):
        """测试使用指定凭证ID获取Token"""
        expected_token = "test_token_67890"
        self.mock_auto_token_service.acquire_token_if_needed.return_value = expected_token
        
        service = ServiceLocator.get_auto_token_acquisition_service()
        token = await service.acquire_token_if_needed("court_zxfw", credential_id=1)
        
        assert token == expected_token
        self.mock_auto_token_service.acquire_token_if_needed.assert_called_once_with("court_zxfw", credential_id=1)
    
    @pytest.mark.asyncio
    async def test_no_available_account_error(self):
        """测试无可用账号异常"""
        self.mock_auto_token_service.acquire_token_if_needed.side_effect = NoAvailableAccountError()
        
        service = ServiceLocator.get_auto_token_acquisition_service()
        
        with pytest.raises(NoAvailableAccountError):
            await service.acquire_token_if_needed("court_zxfw")
    
    @pytest.mark.asyncio
    async def test_auto_token_acquisition_error(self):
        """测试Token获取失败异常"""
        self.mock_auto_token_service.acquire_token_if_needed.side_effect = AutoTokenAcquisitionError("获取失败")
        
        service = ServiceLocator.get_auto_token_acquisition_service()
        
        with pytest.raises(AutoTokenAcquisitionError):
            await service.acquire_token_if_needed("court_zxfw")

# 集成测试示例
@pytest.mark.django_db
class TestBusinessServiceIntegration:
    """业务服务集成测试"""
    
    def setup_method(self):
        ServiceLocator.clear()
    
    def teardown_method(self):
        ServiceLocator.clear()
    
    @pytest.mark.asyncio
    async def test_document_service_integration(self):
        """测试文档服务集成"""
        # 创建Mock自动Token服务
        mock_service = Mock(spec=IAutoTokenAcquisitionService)
        mock_service.acquire_token_if_needed.return_value = "test_token"
        
        # 注入Mock服务
        ServiceLocator.register("auto_token_acquisition_service", mock_service)
        
        # 创建文档服务
        from examples.business_service_integration import DocumentService
        doc_service = DocumentService()
        
        # Mock下载方法
        doc_service._download_with_token = AsyncMock(return_value={
            "document_id": "DOC123",
            "status": "success"
        })
        
        # 执行测试
        result = await doc_service.download_document("DOC123")
        
        # 验证结果
        assert result["status"] == "success"
        mock_service.acquire_token_if_needed.assert_called_once()

# 性能测试示例
class TestPerformanceOptimization:
    """性能优化测试"""
    
    @pytest.mark.asyncio
    async def test_cache_performance(self):
        """测试缓存性能"""
        from examples.performance_optimization import OptimizedTokenService
        
        # 创建Mock服务
        mock_service = Mock(spec=IAutoTokenAcquisitionService)
        mock_service.acquire_token_if_needed.return_value = "cached_token"
        
        ServiceLocator.register("auto_token_acquisition_service", mock_service)
        
        # 创建优化服务
        opt_service = OptimizedTokenService()
        
        # 首次获取
        token1 = await opt_service.get_token_optimized("court_zxfw")
        
        # 再次获取（应该命中本地缓存）
        token2 = await opt_service.get_token_optimized("court_zxfw")
        
        # 验证结果
        assert token1 == token2
        # 应该只调用一次自动Token服务（第二次命中缓存）
        mock_service.acquire_token_if_needed.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_batch_token_acquisition(self):
        """测试批量Token获取"""
        from examples.performance_optimization import OptimizedTokenService
        
        mock_service = Mock(spec=IAutoTokenAcquisitionService)
        mock_service.acquire_token_if_needed.return_value = "batch_token"
        
        ServiceLocator.register("auto_token_acquisition_service", mock_service)
        
        opt_service = OptimizedTokenService()
        
        # 批量获取
        requests = [
            ("court_zxfw", None),
            ("court_zxfw", 1),
            ("other_site", None)
        ]
        
        results = await opt_service.batch_get_tokens(requests)
        
        # 验证结果
        assert len(results) == 3
        assert all(token == "batch_token" for token in results.values() if token)

# 运行测试
if __name__ == "__main__":
    # 运行单个测试
    pytest.main([__file__ + "::TestAutoTokenIntegration::test_successful_token_acquisition", "-v"])
```

## 总结

这些示例代码展示了自动Token获取功能在各种场景下的使用方法：

1. **基础使用**: 简单的Token获取和指定凭证使用
2. **服务集成**: 在业务服务中集成自动Token获取功能
3. **API集成**: 在Django Ninja API中的集成方式
4. **错误处理**: 完整的错误处理和降级策略
5. **性能优化**: 多级缓存和批量处理
6. **监控调试**: 系统健康监控和诊断工具
7. **测试示例**: 单元测试、集成测试和性能测试

通过这些示例，开发者可以：

- 快速理解如何使用自动Token获取功能
- 学习最佳实践和常见模式
- 了解如何处理各种异常情况
- 掌握性能优化技巧
- 编写完整的测试用例

这些示例代码可以直接在项目中使用，或作为开发新功能的参考模板。