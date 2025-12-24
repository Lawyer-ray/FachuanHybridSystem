"""
法院保险询价 API 客户端

提供与法院保险系统的 API 交互功能：
- 获取保险公司列表
- 查询单个保险公司报价
- 并发查询所有保险公司报价
"""
import logging
import asyncio
from typing import List, Optional, Dict
from decimal import Decimal
from dataclasses import dataclass
import httpx

from apps.core.interfaces import ITokenService
from apps.core.exceptions import TokenError, APIError, NetworkError
from apps.core.config import get_config

logger = logging.getLogger("apps.automation")


@dataclass
class InsuranceCompany:
    """保险公司信息"""
    c_id: str
    c_code: str
    c_name: str


@dataclass
class PremiumResult:
    """报价结果"""
    company: InsuranceCompany
    premium: Optional[Decimal]
    status: str  # "success" or "failed"
    error_message: Optional[str]
    response_data: Optional[Dict]
    request_info: Optional[Dict] = None  # 请求信息（用于调试）


class CourtInsuranceClient:
    """
    法院保险询价 API 客户端
    
    使用 httpx 异步客户端进行 HTTP 请求，支持并发查询多个保险公司报价。
    
    性能优化：
    - 使用共享的 httpx.AsyncClient 实现连接池复用
    - 配置连接池参数优化并发性能
    - 支持 HTTP/2 多路复用
    """
    
    # 配置将从统一配置管理系统获取
    # 这些常量保留作为默认值，实际使用时会从配置系统读取
    
    def __init__(self, token_service: Optional[ITokenService] = None):
        """
        初始化客户端（使用依赖注入）
        
        Args:
            token_service: Token 管理服务（可选）。
                          如果不提供则使用 ServiceLocator 获取。
                          建议在生产环境中注入以便于测试和管理。
        
        Example:
            # 使用默认 TokenService（通过 ServiceLocator）
            client = CourtInsuranceClient()
            
            # 注入自定义 TokenService（推荐用于测试）
            client = CourtInsuranceClient(token_service=mock_token_service)
        """
        self._token_service = token_service
    
        # 创建共享的 httpx 客户端，配置连接池
        # 使用 Limits 配置连接池参数
        max_connections = self.max_connections
        max_keepalive_connections = get_config("services.insurance.max_keepalive_connections", 20)
        keepalive_expiry = get_config("services.insurance.keepalive_expiry", 30.0)
        
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=keepalive_expiry,
        )
        
        # 创建共享客户端（尝试启用 HTTP/2）
        # HTTP/2 需要安装 h2 包: pip install httpx[http2]
        try:
            self._client = httpx.AsyncClient(
                limits=limits,
                timeout=self.default_timeout,
                http2=True,  # 启用 HTTP/2 支持
                follow_redirects=True,
            )
            http2_enabled = True
        except ImportError:
            # h2 包未安装，回退到 HTTP/1.1
            logger.warning(
                "h2 包未安装，HTTP/2 已禁用。建议安装: pip install httpx[http2]",
                extra={"action": "client_init_http2_fallback"}
            )
            self._client = httpx.AsyncClient(
                limits=limits,
                timeout=self.default_timeout,
                http2=False,
                follow_redirects=True,
            )
            http2_enabled = False
        
        logger.info(
            "✅ httpx 客户端已初始化",
            extra={
                "action": "client_init",
                "max_connections": max_connections,
                "max_keepalive_connections": max_keepalive_connections,
                "keepalive_expiry": keepalive_expiry,
                "default_timeout": self.default_timeout,
                "http2_enabled": http2_enabled,
            }
        )
    
    @property
    def token_service(self) -> ITokenService:
        """获取 Token 服务（延迟加载）"""
        if self._token_service is None:
            from apps.core.interfaces import ServiceLocator
            self._token_service = ServiceLocator.get_token_service()
        return self._token_service
    
    @property
    def insurance_list_url(self) -> str:
        """获取保险公司列表 API URL"""
        return get_config(
            "services.insurance.list_url",
            "https://baoquan.court.gov.cn/wsbq/ssbq/api/commoncodepz"
        )
    
    @property
    def premium_query_url(self) -> str:
        """获取保险费率查询 API URL"""
        return get_config(
            "services.insurance.premium_query_url",
            "https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium"
        )
    
    @property
    def default_timeout(self) -> float:
        """获取默认超时时间"""
        return get_config("services.insurance.default_timeout", 60.0)
    
    @property
    def max_connections(self) -> int:
        """获取最大连接数"""
        return get_config("services.insurance.max_connections", 100)
    
    async def close(self):
        """
        关闭客户端，释放连接池资源
        
        应该在应用关闭时调用此方法
        """
        await self._client.aclose()
        logger.info("httpx 客户端已关闭")
    
    async def __aenter__(self):
        """支持异步上下文管理器"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """支持异步上下文管理器"""
        await self.close()
    
    async def fetch_insurance_companies(
        self,
        bearer_token: str,
        c_pid: str,
        fy_id: str,
        timeout: float = None,
        max_retries: int = 3
    ) -> List[InsuranceCompany]:
        """
        获取保险公司列表（带重试）
        
        Args:
            bearer_token: Bearer Token
            c_pid: 分类 ID
            fy_id: 法院 ID
            timeout: 超时时间（秒），默认使用 DEFAULT_TIMEOUT
            max_retries: 最大重试次数（默认 3 次）
            
        Returns:
            保险公司列表
            
        Raises:
            NetworkError: 网络错误（连接失败、超时等），会自动重试
            APIError: API 错误（HTTP 状态码错误、响应格式错误等），不会重试
            TokenError: Token 错误（Token 无效、过期等），不会重试
        """
        if timeout is None:
            timeout = self.default_timeout
        
        # 重试逻辑
        last_exception = None
        for attempt in range(1, max_retries + 1):
            try:
                return await self._fetch_insurance_companies_once(
                    bearer_token=bearer_token,
                    c_pid=c_pid,
                    fy_id=fy_id,
                    timeout=timeout,
                    attempt=attempt,
                )
            except NetworkError as e:
                # 网络错误可以重试
                last_exception = e
                if attempt < max_retries:
                    retry_delay = attempt * 2  # 递增延迟：2秒、4秒、6秒
                    logger.warning(
                        f"获取保险公司列表失败（尝试 {attempt}/{max_retries}），{retry_delay}秒后重试: {e.message}",
                        extra={
                            "action": "fetch_insurance_companies_retry",
                            "attempt": attempt,
                            "max_retries": max_retries,
                            "retry_delay": retry_delay,
                            "error_code": e.code,
                        }
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        f"获取保险公司列表失败，已达最大重试次数 {max_retries}",
                        extra={
                            "action": "fetch_insurance_companies_max_retries",
                            "max_retries": max_retries,
                            "error_code": e.code,
                        }
                    )
            except (APIError, TokenError) as e:
                # API 错误和 Token 错误不重试，直接抛出
                logger.error(
                    f"获取保险公司列表失败（不可重试）: {e.message}",
                    extra={
                        "action": "fetch_insurance_companies_non_retryable",
                        "error_code": e.code,
                        "error_type": type(e).__name__,
                    }
                )
                raise
        
        # 所有重试都失败，抛出最后一个异常
        if last_exception:
            raise last_exception
    
    async def _fetch_insurance_companies_once(
        self,
        bearer_token: str,
        c_pid: str,
        fy_id: str,
        timeout: float,
        attempt: int = 1
    ) -> List[InsuranceCompany]:
        """
        获取保险公司列表（单次尝试）
        
        Args:
            bearer_token: Bearer Token
            c_pid: 分类 ID
            fy_id: 法院 ID
            timeout: 超时时间（秒）
            attempt: 当前尝试次数
            
        Returns:
            保险公司列表
            
        Raises:
            NetworkError: 网络错误（连接失败、超时等）
            APIError: API 错误（HTTP 状态码错误、响应格式错误等）
        """
        
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        
        params = {
            "cPid": c_pid,
            "fyId": fy_id,
        }
        
        # 控制台打印：获取保险公司列表请求
        print("\n" + "=" * 100)
        print("🏢 【获取保险公司列表】请求")
        print("=" * 100)
        print(f"📍 URL: {self.insurance_list_url}")
        print(f"📋 URL 参数:")
        print(f"   - cPid: {params['cPid']}")
        print(f"   - fyId: {params['fyId']}")
        print(f"🔑 Bearer Token (前30字符): {bearer_token[:30]}...")
        print(f"📤 HTTP 方法: GET")
        print("=" * 100 + "\n")
        
        # 记录 API 调用开始（包含 URL 和参数）
        logger.info(
            "开始获取保险公司列表",
            extra={
                "action": "fetch_insurance_companies_start",
                "url": self.insurance_list_url,
                "params": params,
                "timeout": timeout,
            }
        )
        
        try:
            import time
            start_time = time.time()
            
            # 使用共享客户端（连接池复用）
            response = await self._client.get(
                self.insurance_list_url,
                headers=headers,
                params=params,
                timeout=timeout,
            )
                
            elapsed_time = time.time() - start_time
            
            # 控制台打印：响应信息
            print("\n" + "=" * 100)
            print("📥 【获取保险公司列表】响应")
            print("=" * 100)
            print(f"📊 HTTP 状态码: {response.status_code}")
            print(f"🔗 完整 URL: {response.url}")
            print(f"⏱️ 响应时间: {round(elapsed_time, 3)}秒")
            print(f"📄 响应内容 (前1000字符):")
            print(f"   {response.text[:1000]}")
            print("=" * 100 + "\n")
            
            # 记录 API 调用响应（包含状态码和响应时间）
            response_size = len(response.content) if hasattr(response.content, '__len__') else 0
            logger.info(
                "保险公司列表 API 响应",
                extra={
                    "action": "fetch_insurance_companies_response",
                    "url": self.insurance_list_url,
                    "status_code": response.status_code,
                    "response_time_seconds": round(elapsed_time, 3),
                    "response_size_bytes": response_size,
                }
            )
                
            # 检查 HTTP 状态码
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(
                    "获取保险公司列表失败",
                    extra={
                        "action": "fetch_insurance_companies_error",
                        "url": self.insurance_list_url,
                        "status_code": response.status_code,
                        "error_message": error_msg,
                        "response_time_seconds": round(elapsed_time, 3),
                    }
                )
                raise httpx.HTTPStatusError(
                    error_msg,
                    request=response.request,
                    response=response
                )
            
            # 解析响应
            data = response.json()
            
            # 提取保险公司列表
            companies = []
            if isinstance(data, dict) and "data" in data:
                company_list = data.get("data", [])
            elif isinstance(data, list):
                company_list = data
            else:
                logger.warning(f"未知的响应格式: {data}")
                company_list = []
            
            # 解析每个保险公司
            for item in company_list:
                if not isinstance(item, dict):
                    continue
                
                c_id = item.get("cId")
                c_code = item.get("cCode")
                c_name = item.get("cName")
                
                # 验证必需字段
                if c_id and c_code and c_name:
                    companies.append(
                        InsuranceCompany(
                            c_id=str(c_id),
                            c_code=str(c_code),
                            c_name=str(c_name),
                        )
                    )
                else:
                    logger.warning(
                        f"保险公司信息不完整，跳过: {item}"
                    )
            
            logger.info(
                f"✅ 成功获取 {len(companies)} 家保险公司",
                extra={
                    "action": "fetch_insurance_companies_success",
                    "companies_count": len(companies),
                    "total_time_seconds": round(elapsed_time, 3),
                }
            )
            
            if not companies:
                logger.warning(
                    "保险公司列表为空",
                    extra={
                        "action": "fetch_insurance_companies_empty",
                        "c_pid": c_pid,
                        "fy_id": fy_id,
                    }
                )
            
            return companies
        
        except httpx.TimeoutException as e:
            error_msg = f"获取保险公司列表超时（{timeout}秒）"
            logger.error(
                error_msg,
                extra={
                    "action": "fetch_insurance_companies_timeout",
                    "url": self.insurance_list_url,
                    "timeout": timeout,
                    "error_type": type(e).__name__,
                },
                exc_info=True
            )
            raise NetworkError(
                message=error_msg,
                code="INSURANCE_LIST_TIMEOUT",
                errors={
                    "url": self.insurance_list_url,
                    "timeout": timeout,
                    "original_error": str(e)
                }
            )
        except httpx.HTTPStatusError as e:
            error_msg = f"获取保险公司列表失败: HTTP {e.response.status_code}"
            
            # 5xx服务器错误可以重试（502 Bad Gateway, 503 Service Unavailable, 504 Gateway Timeout等）
            if 500 <= e.response.status_code < 600:
                logger.warning(
                    f"服务器错误（可重试）: {error_msg}",
                    extra={
                        "action": "fetch_insurance_companies_server_error",
                        "url": self.insurance_list_url,
                        "status_code": e.response.status_code,
                        "error_type": type(e).__name__,
                    }
                )
                raise NetworkError(
                    message=error_msg,
                    code="INSURANCE_LIST_SERVER_ERROR",
                    errors={
                        "url": self.insurance_list_url,
                        "status_code": e.response.status_code,
                        "response_text": e.response.text[:500] if e.response.text else "",
                        "original_error": str(e)
                    }
                )
            
            # 4xx客户端错误不重试
            logger.error(
                error_msg,
                extra={
                    "action": "fetch_insurance_companies_http_status_error",
                    "url": self.insurance_list_url,
                    "status_code": e.response.status_code,
                    "error_type": type(e).__name__,
                },
                exc_info=True
            )
            raise APIError(
                message=error_msg,
                code="INSURANCE_LIST_HTTP_ERROR",
                errors={
                    "url": self.insurance_list_url,
                    "status_code": e.response.status_code,
                    "response_text": e.response.text[:500] if e.response.text else "",
                    "original_error": str(e)
                }
            )
        except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
            error_msg = f"获取保险公司列表网络错误: {type(e).__name__}"
            logger.error(
                error_msg,
                extra={
                    "action": "fetch_insurance_companies_network_error",
                    "url": self.insurance_list_url,
                    "error_type": type(e).__name__,
                },
                exc_info=True
            )
            raise NetworkError(
                message=error_msg,
                code="INSURANCE_LIST_NETWORK_ERROR",
                errors={
                    "url": self.insurance_list_url,
                    "error_type": type(e).__name__,
                    "original_error": str(e)
                }
            )
        except httpx.HTTPError as e:
            error_msg = f"获取保险公司列表 HTTP 错误: {type(e).__name__}"
            logger.error(
                error_msg,
                extra={
                    "action": "fetch_insurance_companies_http_error",
                    "url": self.insurance_list_url,
                    "error_type": type(e).__name__,
                },
                exc_info=True
            )
            raise NetworkError(
                message=error_msg,
                code="INSURANCE_LIST_HTTP_ERROR",
                errors={
                    "url": self.insurance_list_url,
                    "error_type": type(e).__name__,
                    "original_error": str(e)
                }
            )
        except Exception as e:
            error_msg = f"获取保险公司列表失败: {type(e).__name__}"
            logger.error(
                error_msg,
                extra={
                    "action": "fetch_insurance_companies_exception",
                    "url": self.insurance_list_url,
                    "error_type": type(e).__name__,
                },
                exc_info=True
            )
            raise APIError(
                message=error_msg,
                code="INSURANCE_LIST_ERROR",
                errors={
                    "url": self.insurance_list_url,
                    "error_type": type(e).__name__,
                    "original_error": str(e)
                }
            )
    
    async def fetch_premium(
        self,
        bearer_token: str,
        preserve_amount: Decimal,
        institution: str,
        corp_id: str,
        timeout: float = None
    ) -> PremiumResult:
        """
        查询单个保险公司报价
        
        注意：此方法不会抛出异常，而是返回包含错误信息的 PremiumResult。
        这样设计是为了支持并发查询时，单个查询失败不影响其他查询。
        
        Args:
            bearer_token: Bearer Token
            preserve_amount: 保全金额
            institution: 保险公司编码 (cCode)
            corp_id: 企业/法院 ID
            timeout: 超时时间（秒），默认使用 DEFAULT_TIMEOUT
            
        Returns:
            报价结果（包含成功或失败信息）
            - status="success": 查询成功，premium 字段包含报价金额
            - status="failed": 查询失败，error_message 字段包含详细错误信息
        """
        if timeout is None:
            timeout = self.default_timeout
        
        import time
        
        # 生成毫秒级时间戳（关键修复！）
        current_time_ms = str(int(time.time() * 1000))
        
        # 请求头（修复：Bearer 字段而不是 Authorization）
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Bearer": bearer_token,  # 修复：直接使用 Bearer 字段
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://zxfw.court.gov.cn",
            "Pragma": "no-cache",
            "Referer": "https://zxfw.court.gov.cn/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }
        
        # 转换保全金额为整数字符串（去掉小数点，API 要求整数）
        # 如果 preserve_amount 是 Decimal("3.00")，转换为 "3"
        preserve_amount_str = str(int(preserve_amount))
        
        # URL 查询参数（修复：添加时间戳）
        params = {
            "time": current_time_ms,  # 修复：添加毫秒级时间戳
            "preserveAmount": preserve_amount_str,
            "institution": institution,
            "corpId": corp_id,
        }
        
        # 请求体数据（修复：POST 请求需要请求体）
        request_body = {
            "preserveAmount": preserve_amount_str,
            "institution": institution,
            "corpId": corp_id,
        }
        
        # 创建临时的 InsuranceCompany 对象（用于返回结果）
        company = InsuranceCompany(
            c_id="",  # 单个查询时不需要 cId
            c_code=institution,
            c_name="",  # 单个查询时不需要 cName
        )
        
        # 构建请求信息（用于记录）
        request_info = {
            "url": self.premium_query_url,
            "method": "POST",
            "timestamp": current_time_ms,
            "params": params.copy(),
            "body": request_body.copy(),
            "headers": {k: v[:50] + "..." if k == "Bearer" and len(v) > 50 else v for k, v in headers.items()},
            "timeout": timeout if timeout else self.default_timeout,
        }
        
        # 控制台打印：完整的询价请求信息
        import json
        print("\n" + "=" * 120)
        print(f"💰 【询价请求】保险公司: {institution}")
        print("=" * 120)
        print(f"📍 完整 URL: {self.premium_query_url}?time={params['time']}&preserveAmount={params['preserveAmount']}&institution={params['institution']}&corpId={params['corpId']}")
        print(f"⏰ 时间戳: {current_time_ms}")
        print(f"\n📋 URL 查询参数:")
        for key, value in params.items():
            print(f"   {key}: {value} (类型: {type(value).__name__})")
        
        print(f"\n📦 请求体 (JSON):")
        print(json.dumps(request_body, ensure_ascii=False, indent=2))
        
        print(f"\n🔑 完整请求头:")
        for key, value in headers.items():
            if key == "Bearer":
                print(f"   {key}: {value[:50]}...{value[-30:]}")
            else:
                print(f"   {key}: {value}")
        
        print(f"\n📤 HTTP 方法: POST")
        print(f"📄 Content-Type: {headers['Content-Type']}")
        print(f"⏱️ 超时时间: {timeout if timeout else self.default_timeout} 秒")
        print("=" * 120 + "\n")
        
        # 记录完整的请求信息（用于调试）
        logger.info(
            f"=" * 80 + "\n"
            f"🔍 查询保险公司报价: {institution}\n"
            f"=" * 80 + "\n"
            f"📍 URL: {self.premium_query_url}\n"
            f"⏰ 时间戳: {current_time_ms}\n"
            f"📋 URL 参数:\n"
            f"   - time: {params['time']}\n"
            f"   - preserveAmount: {params['preserveAmount']}\n"
            f"   - institution: {params['institution']}\n"
            f"   - corpId: {params['corpId']}\n"
            f"📦 请求体:\n"
            f"   {request_body}\n"
            f"🔑 Bearer Token (前20字符): {bearer_token[:20]}...\n"
            f"=" * 80
        )
        
        try:
            start_time = time.time()
            
            # 修复：使用 POST 请求而不是 GET
            response = await self._client.post(
                self.premium_query_url,
                headers=headers,
                params=params,
                json=request_body,  # 修复：添加请求体
                timeout=timeout,
            )
            
            # 控制台打印：完整的响应信息
            elapsed = round(time.time() - start_time, 3)
            print("\n" + "=" * 120)
            print(f"📥 【询价响应】保险公司: {institution}")
            print("=" * 120)
            print(f"📊 HTTP 状态码: {response.status_code}")
            print(f"🔗 完整 URL: {response.url}")
            print(f"⏱️ 响应时间: {elapsed} 秒")
            
            print(f"\n📋 响应头:")
            for key, value in response.headers.items():
                print(f"   {key}: {value}")
            
            print(f"\n📄 完整响应内容:")
            print(response.text)
            
            print(f"\n📦 响应内容 (格式化 JSON):")
            try:
                response_json = response.json()
                print(json.dumps(response_json, ensure_ascii=False, indent=2))
            except:
                print("   (无法解析为 JSON)")
            
            print("=" * 120 + "\n")
            
            # 记录完整的响应信息
            logger.info(
                f"=" * 80 + "\n"
                f"📥 API 响应: {institution}\n"
                f"=" * 80 + "\n"
                f"📊 状态码: {response.status_code}\n"
                f"🔗 完整 URL: {response.url}\n"
                f"📄 响应内容: {response.text[:500]}\n"
                f"⏱️ 响应时间: {round(time.time() - start_time, 3)}秒\n"
                f"=" * 80
            )
                
            elapsed_time = time.time() - start_time
            
            # 记录 API 调用响应（包含状态码和响应时间）
            response_size = len(response.content) if hasattr(response.content, '__len__') else 0
            logger.info(
                f"保险公司 {institution} 响应",
                extra={
                    "action": "fetch_premium_response",
                    "url": self.premium_query_url,
                    "institution": institution,
                    "status_code": response.status_code,
                    "response_time_seconds": round(elapsed_time, 3),
                    "response_size_bytes": response_size,
                }
            )
            
            # 检查 HTTP 状态码
            if response.status_code != 200:
                # 构建详细的错误信息
                error_details = {
                    "error": f"HTTP {response.status_code}",
                    "request": request_info,
                    "response": {
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "body": response.text,
                        "elapsed_seconds": round(elapsed_time, 3),
                    }
                }
                error_msg = json.dumps(error_details, ensure_ascii=False, indent=2)
                
                logger.warning(
                    f"保险公司 {institution} 查询失败: HTTP {response.status_code}",
                    extra={
                        "action": "fetch_premium_http_error",
                        "institution": institution,
                        "status_code": response.status_code,
                        "response_time_seconds": round(elapsed_time, 3),
                    }
                )
                return PremiumResult(
                    company=company,
                    premium=None,
                    status="failed",
                    error_message=error_msg,
                    response_data=None,
                    request_info=request_info,
                )
            
            # 解析响应
            data = response.json()
            
            # 提取 data 字段中的费率信息
            rate_data = data.get("data", {}) if isinstance(data, dict) else {}
            
            # 控制台打印：费率信息详情
            if rate_data:
                print("\n" + "=" * 100)
                print(f"💰 【费率信息详情】保险公司: {institution}")
                print("=" * 100)
                print(f"  最低收费1 (minPremium):        {rate_data.get('minPremium', 'N/A')} 元")
                print(f"  最低收费2 (minAmount):         {rate_data.get('minAmount', 'N/A')} 元")
                print(f"  最低费率 (minRate):            {rate_data.get('minRate', 'N/A')}")
                print(f"  最高费率 (maxRate):            {rate_data.get('maxRate', 'N/A')}")
                print(f"  最高收费 (maxAmount):          {rate_data.get('maxAmount', 'N/A')} 元")
                print(f"  最高保全金额 (maxApplyAmount): {rate_data.get('maxApplyAmount', 'N/A')} 元")
                print("=" * 100 + "\n")
            
            # 提取报价金额（优先使用 minPremium）
            premium = None
            if rate_data:
                # 优先使用 minPremium 作为报价
                premium_value = rate_data.get("minPremium") or rate_data.get("minAmount")
                if premium_value is not None:
                    try:
                        premium = Decimal(str(premium_value))
                    except (ValueError, TypeError) as e:
                        logger.warning(f"无法解析报价金额: {premium_value}, 错误: {e}")
            
            if premium is not None:
                # 构建成功的详细信息（包含请求和响应）
                success_details = {
                    "status": "success",
                    "request": request_info,
                    "response": {
                        "status_code": response.status_code,
                        "body": data,
                        "elapsed_seconds": round(elapsed_time, 3),
                    }
                }
                success_msg = json.dumps(success_details, ensure_ascii=False, indent=2)
                
                logger.info(
                    f"✅ 保险公司 {institution} 报价: ¥{premium}",
                    extra={
                        "action": "fetch_premium_success",
                        "institution": institution,
                        "premium": str(premium),
                        "min_premium": rate_data.get("minPremium"),
                        "min_amount": rate_data.get("minAmount"),
                        "min_rate": rate_data.get("minRate"),
                        "max_rate": rate_data.get("maxRate"),
                        "max_amount": rate_data.get("maxAmount"),
                        "max_apply_amount": rate_data.get("maxApplyAmount"),
                        "response_time_seconds": round(elapsed_time, 3),
                    }
                )
                return PremiumResult(
                    company=company,
                    premium=premium,
                    status="success",
                    error_message=success_msg,  # 成功时也记录完整信息
                    response_data=data,
                    request_info=request_info,
                )
            else:
                # 构建详细的错误信息
                error_details = {
                    "error": "响应中未找到费率数据",
                    "request": request_info,
                    "response": {
                        "status_code": response.status_code,
                        "body": data,
                        "elapsed_seconds": round(elapsed_time, 3),
                    }
                }
                error_msg = json.dumps(error_details, ensure_ascii=False, indent=2)
                
                logger.warning(
                    f"保险公司 {institution}: 响应中未找到费率数据",
                    extra={
                        "action": "fetch_premium_no_premium",
                        "institution": institution,
                        "response_time_seconds": round(elapsed_time, 3),
                    }
                )
                return PremiumResult(
                    company=company,
                    premium=None,
                    status="failed",
                    error_message=error_msg,
                    response_data=data,
                    request_info=request_info,
                )
        
        except httpx.TimeoutException as e:
            # 构建详细的错误信息
            error_details = {
                "error": "查询超时",
                "exception": str(e),
                "exception_type": type(e).__name__,
                "request": request_info,
            }
            error_msg = json.dumps(error_details, ensure_ascii=False, indent=2)
            
            logger.warning(
                f"保险公司 {institution} 查询超时",
                extra={
                    "action": "fetch_premium_timeout",
                    "institution": institution,
                    "timeout": timeout,
                    "error_type": type(e).__name__,
                }
            )
            return PremiumResult(
                company=company,
                premium=None,
                status="failed",
                error_message=error_msg,
                response_data=None,
                request_info=request_info,
            )
        except httpx.HTTPError as e:
            # 构建详细的错误信息
            error_details = {
                "error": "HTTP 错误",
                "exception": str(e),
                "exception_type": type(e).__name__,
                "request": request_info,
            }
            error_msg = json.dumps(error_details, ensure_ascii=False, indent=2)
            
            logger.warning(
                f"保险公司 {institution} HTTP 错误",
                extra={
                    "action": "fetch_premium_http_exception",
                    "institution": institution,
                    "error_type": type(e).__name__,
                }
            )
            return PremiumResult(
                company=company,
                premium=None,
                status="failed",
                error_message=error_msg,
                response_data=None,
                request_info=request_info,
            )
        except Exception as e:
            # 构建详细的错误信息
            import traceback
            error_details = {
                "error": "未知错误",
                "exception": str(e),
                "exception_type": type(e).__name__,
                "traceback": traceback.format_exc(),
                "request": request_info,
            }
            error_msg = json.dumps(error_details, ensure_ascii=False, indent=2)
            
            logger.error(
                f"保险公司 {institution} 未知错误",
                extra={
                    "action": "fetch_premium_exception",
                    "institution": institution,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True  # 记录完整堆栈信息
            )
            return PremiumResult(
                company=company,
                premium=None,
                status="failed",
                error_message=error_msg,
                response_data=None,
                request_info=request_info,
            )
    
    async def fetch_all_premiums(
        self,
        bearer_token: str,
        preserve_amount: Decimal,
        corp_id: str,
        companies: List[InsuranceCompany],
        timeout: float = None
    ) -> List[PremiumResult]:
        """
        并发查询所有保险公司报价
        
        使用 asyncio.gather 并发执行所有查询，单个查询失败不影响其他查询。
        
        Args:
            bearer_token: Bearer Token
            preserve_amount: 保全金额
            corp_id: 企业/法院 ID
            companies: 保险公司列表
            timeout: 超时时间（秒），默认使用 DEFAULT_TIMEOUT
            
        Returns:
            所有保险公司的报价结果列表
        """
        if not companies:
            logger.warning(
                "保险公司列表为空，无法查询报价",
                extra={
                    "action": "fetch_all_premiums_empty",
                }
            )
            return []
        
        # 记录并发查询开始
        logger.info(
            f"开始并发查询 {len(companies)} 家保险公司报价",
            extra={
                "action": "fetch_all_premiums_start",
                "preserve_amount": str(preserve_amount),
                "corp_id": corp_id,
                "total_companies": len(companies),
                "timeout": timeout,
            }
        )
        
        # 使用分批并发 + 延迟策略，避免请求过快
        import time
        start_time = time.time()
        
        # 配置：每批并发数量和批次间延迟
        BATCH_SIZE = 2  # 每批最多2个并发请求（降低并发数）
        BATCH_DELAY = 2.0  # 批次间延迟2秒（增加延迟）
        REQUEST_DELAY = 0.5  # 同一批次内请求间延迟0.5秒（增加延迟）
        
        logger.info(
            f"使用分批并发策略: 每批{BATCH_SIZE}个请求，批次间延迟{BATCH_DELAY}秒，请求间延迟{REQUEST_DELAY}秒",
            extra={
                "action": "fetch_all_premiums_batch_strategy",
                "batch_size": BATCH_SIZE,
                "batch_delay": BATCH_DELAY,
                "request_delay": REQUEST_DELAY,
            }
        )
        
        results = []
        
        # 分批处理
        for batch_idx in range(0, len(companies), BATCH_SIZE):
            batch_companies = companies[batch_idx:batch_idx + BATCH_SIZE]
            batch_num = batch_idx // BATCH_SIZE + 1
            total_batches = (len(companies) + BATCH_SIZE - 1) // BATCH_SIZE
            
            logger.info(
                f"处理第 {batch_num}/{total_batches} 批，包含 {len(batch_companies)} 家保险公司",
                extra={
                    "action": "fetch_all_premiums_batch_start",
                    "batch_num": batch_num,
                    "total_batches": total_batches,
                    "batch_size": len(batch_companies),
                }
            )
            
            # 创建当前批次的任务（带延迟）
            batch_tasks = []
            for idx, company in enumerate(batch_companies):
                # 同一批次内的请求也添加小延迟
                if idx > 0:
                    await asyncio.sleep(REQUEST_DELAY)
                
                task = self.fetch_premium(
                    bearer_token=bearer_token,
                    preserve_amount=preserve_amount,
                    institution=company.c_code,
                    corp_id=corp_id,
                    timeout=timeout,
                )
                batch_tasks.append(task)
            
            # 并发执行当前批次
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            results.extend(batch_results)
            
            # 批次间延迟（最后一批不需要延迟）
            if batch_idx + BATCH_SIZE < len(companies):
                logger.info(
                    f"批次 {batch_num} 完成，等待 {BATCH_DELAY} 秒后处理下一批",
                    extra={
                        "action": "fetch_all_premiums_batch_delay",
                        "batch_num": batch_num,
                        "delay_seconds": BATCH_DELAY,
                    }
                )
                await asyncio.sleep(BATCH_DELAY)
        
        elapsed_time = time.time() - start_time
        
        # 处理结果
        premium_results = []
        for i, result in enumerate(results):
            company = companies[i]
            
            if isinstance(result, Exception):
                # 任务抛出异常（记录完整堆栈信息）
                error_msg = f"查询异常: {str(result)}"
                logger.error(
                    f"保险公司 {company.c_name} ({company.c_code}) {error_msg}",
                    extra={
                        "action": "fetch_all_premiums_task_exception",
                        "company_name": company.c_name,
                        "company_code": company.c_code,
                        "error_type": type(result).__name__,
                        "error_message": str(result),
                    },
                    exc_info=result  # 记录完整堆栈信息
                )
                premium_results.append(
                    PremiumResult(
                        company=company,
                        premium=None,
                        status="failed",
                        error_message=error_msg,
                        response_data=None,
                    )
                )
            elif isinstance(result, PremiumResult):
                # 正常返回结果，补充公司信息
                result.company.c_id = company.c_id
                result.company.c_name = company.c_name
                premium_results.append(result)
            else:
                # 未知结果类型
                error_msg = f"未知结果类型: {type(result)}"
                logger.error(
                    f"保险公司 {company.c_name} ({company.c_code}) {error_msg}",
                    extra={
                        "action": "fetch_all_premiums_unknown_result",
                        "company_name": company.c_name,
                        "company_code": company.c_code,
                        "result_type": str(type(result)),
                    }
                )
                premium_results.append(
                    PremiumResult(
                        company=company,
                        premium=None,
                        status="failed",
                        error_message=error_msg,
                        response_data=None,
                    )
                )
        
        # 统计结果
        success_count = sum(1 for r in premium_results if r.status == "success")
        failed_count = len(premium_results) - success_count
        
        # 记录并发查询完成（包含执行时长和统计信息）
        logger.info(
            f"✅ 并发查询完成",
            extra={
                "action": "fetch_all_premiums_complete",
                "total_time_seconds": round(elapsed_time, 2),
                "total_companies": len(companies),
                "success_count": success_count,
                "failed_count": failed_count,
                "success_rate": round(success_count / len(companies) * 100, 2) if companies else 0,
                "avg_time_per_company": round(elapsed_time / len(companies), 3) if companies else 0,
            }
        )
        
        return premium_results
