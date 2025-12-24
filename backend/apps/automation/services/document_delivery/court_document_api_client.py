"""
法院文书 API 客户端

直接调用法院一张网 API 获取文书列表和下载链接，
替代 Playwright 浏览器自动化方式，提升效率。

Requirements: 8.1, 8.2, 8.3, 8.4
"""
import logging
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

import httpx

from apps.core.exceptions import (
    ExternalServiceError,
    NetworkError,
    TokenError,
)
from apps.automation.utils.logging import AutomationLogger

if TYPE_CHECKING:
    from apps.core.interfaces import IAutoLoginService

logger = logging.getLogger("apps.automation")


# ==================== 异常类 ====================

class CourtApiError(ExternalServiceError):
    """法院 API 调用错误"""
    
    def __init__(
        self,
        message: str = "法院 API 调用错误",
        code: Optional[str] = None,
        errors: Optional[dict] = None
    ):
        super().__init__(
            message=message,
            code=code or "COURT_API_ERROR",
            errors=errors or {}
        )


class TokenExpiredError(TokenError):
    """Token 过期错误"""
    
    def __init__(
        self,
        message: str = "Token 已过期",
        code: Optional[str] = None,
        errors: Optional[dict] = None
    ):
        super().__init__(
            message=message,
            code=code or "TOKEN_EXPIRED",
            errors=errors or {}
        )


class ApiResponseError(CourtApiError):
    """API 响应错误"""
    
    def __init__(
        self,
        message: str = "API 响应错误",
        code: Optional[str] = None,
        errors: Optional[dict] = None,
        response_code: Optional[int] = None
    ):
        super().__init__(
            message=message,
            code=code or "API_RESPONSE_ERROR",
            errors=errors or {}
        )
        self.response_code = response_code


# ==================== 数据类 ====================

@dataclass
class DocumentRecord:
    """
    单个文书记录 - 来自 getSdListByZjhmAndAhdmNew
    
    Requirements: 1.2, 3.1
    """
    ah: str                 # 案号，如"（2025）粤0604民初41257号"
    ahdm: str              # 案号代码
    sdbh: str              # 送达编号 - 用于获取文书详情
    ajzybh: str            # 案件主要编号
    fssj: str              # 发送时间，如"2025-12-10 16:25:37" - 用于时间过滤
    fymc: str              # 法院名称
    fybh: str              # 法院编号
    ssdrxm: str            # 送达人姓名
    ssdrsjhm: str          # 送达人手机号
    ssdrzjhm: str          # 送达人证件号码
    wsmc: str              # 文书名称（多个用逗号分隔）
    sdzt: str              # 送达状态
    qdzt: str              # 签到状态
    qdbh: str              # 签到编号
    fqr: str               # 发起人
    cjsj: str              # 创建时间
    zhxgsj: str            # 最后修改时间
    
    def parse_fssj(self) -> Optional[datetime]:
        """解析 fssj 为 datetime"""
        if not self.fssj:
            return None
        try:
            return datetime.strptime(self.fssj, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning(f"无法解析发送时间: {self.fssj}")
            return None
    
    @classmethod
    def from_dict(cls, data: dict) -> "DocumentRecord":
        """从 API 响应字典创建实例"""
        return cls(
            ah=data.get("ah", ""),
            ahdm=data.get("ahdm", ""),
            sdbh=data.get("sdbh", ""),
            ajzybh=data.get("ajzybh", ""),
            fssj=data.get("fssj", ""),
            fymc=data.get("fymc", ""),
            fybh=data.get("fybh", ""),
            ssdrxm=data.get("ssdrxm", ""),
            ssdrsjhm=data.get("ssdrsjhm", ""),
            ssdrzjhm=data.get("ssdrzjhm", ""),
            wsmc=data.get("wsmc", ""),
            sdzt=data.get("sdzt", ""),
            qdzt=data.get("qdzt", ""),
            qdbh=data.get("qdbh", ""),
            fqr=data.get("fqr", ""),
            cjsj=data.get("cjsj", ""),
            zhxgsj=data.get("zhxgsj", ""),
        )


@dataclass
class DocumentDetail:
    """
    文书详情（下载信息）- 来自 getWsListBySdbhNew
    
    Requirements: 2.2
    """
    c_sdbh: str            # 送达编号
    c_stbh: str            # 上传编号（文件路径）
    c_wsbh: str            # 文书编号
    c_wsmc: str            # 文书名称
    c_wjgs: str            # 文件格式（如 pdf）
    c_fybh: str            # 法院编号
    c_fymc: str            # 法院名称
    wjlj: str              # 文件链接（OSS URL，带签名）
    dt_cjsj: str           # 创建时间（ISO格式）
    
    @classmethod
    def from_dict(cls, data: dict) -> "DocumentDetail":
        """从 API 响应字典创建实例"""
        return cls(
            c_sdbh=data.get("c_sdbh", ""),
            c_stbh=data.get("c_stbh", ""),
            c_wsbh=data.get("c_wsbh", ""),
            c_wsmc=data.get("c_wsmc", ""),
            c_wjgs=data.get("c_wjgs", ""),
            c_fybh=data.get("c_fybh", ""),
            c_fymc=data.get("c_fymc", ""),
            wjlj=data.get("wjlj", ""),
            dt_cjsj=data.get("dt_cjsj", ""),
        )


@dataclass
class DocumentListResponse:
    """
    文书列表 API 响应
    
    Requirements: 1.4, 3.4
    """
    total: int                      # data.total - 总数量，用于分页计算
    documents: List[DocumentRecord] # data.data - 文书记录列表


# ==================== API 客户端 ====================

class CourtDocumentApiClient:
    """
    法院文书 API 客户端
    
    直接调用法院一张网 API 获取文书列表和下载链接。
    
    Requirements: 8.1, 8.2, 8.3, 8.4
    """
    
    # API 端点
    LIST_API_URL = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getSdListByZjhmAndAhdmNew"
    DETAIL_API_URL = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
    
    # 默认超时时间（秒）
    DEFAULT_TIMEOUT = 30.0
    
    # 默认重试次数
    DEFAULT_RETRY_COUNT = 1
    
    def __init__(
        self,
        auto_login_service: Optional["IAutoLoginService"] = None,
        timeout: float = DEFAULT_TIMEOUT
    ):
        """
        初始化 API 客户端
        
        Args:
            auto_login_service: 自动登录服务实例（可选，用于依赖注入）
            timeout: 请求超时时间（秒）
            
        Requirements: 8.4
        """
        self._auto_login_service = auto_login_service
        self._timeout = timeout
        
        logger.debug(f"CourtDocumentApiClient 初始化完成, timeout={timeout}")

    
    @property
    def auto_login_service(self) -> "IAutoLoginService":
        """延迟加载自动登录服务"""
        if self._auto_login_service is None:
            from apps.core.interfaces import ServiceLocator
            self._auto_login_service = ServiceLocator.get_auto_login_service()
        return self._auto_login_service
    
    def _make_request(
        self,
        url: str,
        token: str,
        data: dict,
        retry_count: int = DEFAULT_RETRY_COUNT
    ) -> dict:
        """
        发送 HTTP POST 请求（带重试）
        
        Args:
            url: API URL
            token: Authorization token
            data: 请求数据
            retry_count: 重试次数
            
        Returns:
            API 响应 JSON
            
        Raises:
            NetworkError: 网络错误
            TokenExpiredError: Token 过期
            ApiResponseError: API 响应错误
            
        Requirements: 5.1, 5.2, 8.3
        """
        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }
        
        last_error = None
        
        for attempt in range(retry_count + 1):
            try:
                logger.debug(f"API 请求: {url}, attempt={attempt + 1}")
                
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(url, headers=headers, json=data)
                
                # 检查 HTTP 状态码
                if response.status_code == 401:
                    raise TokenExpiredError(
                        message="Token 已过期或无效",
                        errors={"status_code": 401}
                    )
                
                if response.status_code >= 400:
                    logger.error(f"HTTP 错误: {response.status_code}, url={url}")
                    raise ApiResponseError(
                        message=f"HTTP 错误: {response.status_code}",
                        response_code=response.status_code,
                        errors={"status_code": response.status_code}
                    )
                
                return response.json()
                
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"请求超时: {url}, attempt={attempt + 1}, error={str(e)}")
                if attempt < retry_count:
                    continue
                raise NetworkError(
                    message=f"请求超时: {str(e)}",
                    errors={"url": url, "timeout": self._timeout}
                )
                
            except httpx.RequestError as e:
                last_error = e
                logger.warning(f"网络错误: {url}, attempt={attempt + 1}, error={str(e)}")
                if attempt < retry_count:
                    continue
                raise NetworkError(
                    message=f"网络错误: {str(e)}",
                    errors={"url": url}
                )
                
            except (TokenExpiredError, ApiResponseError):
                # 这些错误不重试
                raise
                
            except Exception as e:
                last_error = e
                logger.error(f"未知错误: {url}, error={str(e)}")
                raise CourtApiError(
                    message=f"API 调用失败: {str(e)}",
                    errors={"url": url}
                )
        
        # 不应该到达这里
        raise NetworkError(
            message=f"请求失败: {str(last_error)}",
            errors={"url": url}
        )
    
    def fetch_document_list(
        self,
        token: str,
        page_num: int = 1,
        page_size: int = 20
    ) -> DocumentListResponse:
        """
        获取文书列表（同步方法）
        
        调用 getSdListByZjhmAndAhdmNew 接口获取文书列表。
        
        Args:
            token: 认证令牌（Authorization header）
            page_num: 页码（从 1 开始）
            page_size: 每页数量
            
        Returns:
            DocumentListResponse 包含文书列表和分页信息
            
        Raises:
            TokenExpiredError: Token 过期
            ApiResponseError: API 响应错误
            NetworkError: 网络错误
            
        Requirements: 1.1, 1.2, 1.4, 6.1, 7.1, 7.2
        """
        start_time = time.time()
        api_name = "getSdListByZjhmAndAhdmNew"
        
        # 记录请求开始
        AutomationLogger.log_document_api_request_start(
            api_name=api_name,
            page_num=page_num,
            page_size=page_size
        )
        
        data = {
            "pageNum": page_num,
            "pageSize": page_size
        }
        
        try:
            response = self._make_request(self.LIST_API_URL, token, data)
            
            # 验证响应格式
            code = response.get("code")
            if code != 200:
                processing_time = time.time() - start_time
                error_msg = f"API 返回错误: {response.get('msg', '未知错误')}"
                
                # 记录失败日志
                AutomationLogger.log_document_api_request_failed(
                    api_name=api_name,
                    error_message=error_msg,
                    processing_time=processing_time,
                    response_code=code,
                    page_num=page_num
                )
                
                raise ApiResponseError(
                    message=error_msg,
                    response_code=code,
                    errors={"response": response}
                )
            
            # 解析响应数据
            response_data = response.get("data", {})
            total = response_data.get("total", 0)
            documents_data = response_data.get("data", [])
            
            # 转换为数据类
            documents = []
            for doc_data in documents_data:
                try:
                    # 验证必需字段
                    if not doc_data.get("ah") or not doc_data.get("sdbh") or not doc_data.get("fssj"):
                        logger.warning(f"文书记录缺少必需字段: {doc_data}")
                        continue
                        
                    doc = DocumentRecord.from_dict(doc_data)
                    documents.append(doc)
                except Exception as e:
                    logger.warning(f"解析文书记录失败: {str(e)}, data={doc_data}")
                    continue
            
            processing_time = time.time() - start_time
            
            # 记录成功日志
            AutomationLogger.log_document_api_request_success(
                api_name=api_name,
                response_code=code,
                processing_time=processing_time,
                document_count=len(documents),
                total_count=total,
                page_num=page_num
            )
            
            return DocumentListResponse(total=total, documents=documents)
            
        except (TokenExpiredError, ApiResponseError):
            # 这些异常已经记录了日志，直接抛出
            raise
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # 记录详细错误信息
            AutomationLogger.log_api_error_detail(
                api_name=api_name,
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc(),
                request_params={"page_num": page_num, "page_size": page_size}
            )
            
            raise
    
    def fetch_document_details(
        self,
        token: str,
        sdbh: str,
        sdsin: str = "",
        mm: str = ""
    ) -> List[DocumentDetail]:
        """
        获取文书详情（下载链接）
        
        调用 getWsListBySdbhNew 接口获取文书下载链接。
        
        Args:
            token: 认证令牌
            sdbh: 送达编号
            sdsin: 送达签名（可选）
            mm: 密码（可选）
            
        Returns:
            文书详情列表，包含 wjlj（下载链接）
            
        Raises:
            TokenExpiredError: Token 过期
            ApiResponseError: API 响应错误
            NetworkError: 网络错误
            
        Requirements: 2.1, 2.2, 6.4, 7.1, 7.2
        """
        start_time = time.time()
        api_name = "getWsListBySdbhNew"
        
        # 记录请求开始
        AutomationLogger.log_document_api_request_start(
            api_name=api_name,
            sdbh=sdbh
        )
        
        data = {
            "sdbh": sdbh,
            "sdsin": sdsin,
            "mm": mm
        }
        
        try:
            response = self._make_request(self.DETAIL_API_URL, token, data)
            
            # 验证响应格式
            code = response.get("code")
            if code != 200:
                processing_time = time.time() - start_time
                error_msg = f"API 返回错误: {response.get('msg', '未知错误')}"
                
                # 记录失败日志
                AutomationLogger.log_document_api_request_failed(
                    api_name=api_name,
                    error_message=error_msg,
                    processing_time=processing_time,
                    response_code=code
                )
                
                raise ApiResponseError(
                    message=error_msg,
                    response_code=code,
                    errors={"response": response}
                )
            
            # 解析响应数据
            documents_data = response.get("data", [])
            
            # 转换为数据类
            details = []
            for doc_data in documents_data:
                try:
                    detail = DocumentDetail.from_dict(doc_data)
                    # 验证必需字段
                    if not detail.wjlj:
                        logger.warning(f"文书详情缺少下载链接: {doc_data}")
                        continue
                    details.append(detail)
                except Exception as e:
                    logger.warning(f"解析文书详情失败: {str(e)}, data={doc_data}")
                    continue
            
            processing_time = time.time() - start_time
            
            # 记录成功日志
            AutomationLogger.log_document_api_request_success(
                api_name=api_name,
                response_code=code,
                processing_time=processing_time,
                document_count=len(details)
            )
            
            return details
            
        except (TokenExpiredError, ApiResponseError):
            # 这些异常已经记录了日志，直接抛出
            raise
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # 记录详细错误信息
            AutomationLogger.log_api_error_detail(
                api_name=api_name,
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc(),
                request_params={"sdbh": sdbh}
            )
            
            raise
    
    def download_document(
        self,
        url: str,
        save_path: Path
    ) -> bool:
        """
        下载文书文件（从 OSS URL）
        
        Args:
            url: wjlj 字段的 OSS 下载链接
            save_path: 保存路径
            
        Returns:
            下载是否成功
            
        Requirements: 2.3, 7.1, 7.2
        """
        start_time = time.time()
        document_name = save_path.name
        
        # 记录下载开始
        AutomationLogger.log_document_download_start(
            document_name=document_name,
            url=url
        )
        
        try:
            # 确保目录存在
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 下载文件（OSS URL 不需要 Authorization）
            with httpx.Client(timeout=self._timeout * 2) as client:  # 下载超时加倍
                response = client.get(url)
                
                if response.status_code != 200:
                    processing_time = time.time() - start_time
                    error_msg = f"HTTP 状态码错误: {response.status_code}"
                    
                    AutomationLogger.log_document_download_failed(
                        document_name=document_name,
                        error_message=error_msg,
                        processing_time=processing_time
                    )
                    return False
                
                # 保存文件
                with open(save_path, "wb") as f:
                    f.write(response.content)
                
                file_size = len(response.content)
            
            processing_time = time.time() - start_time
            
            # 记录下载成功
            AutomationLogger.log_document_download_success(
                document_name=document_name,
                file_size=file_size,
                processing_time=processing_time,
                save_path=str(save_path)
            )
            
            return True
            
        except httpx.TimeoutException as e:
            processing_time = time.time() - start_time
            error_msg = f"下载超时: {str(e)}"
            
            AutomationLogger.log_document_download_failed(
                document_name=document_name,
                error_message=error_msg,
                processing_time=processing_time
            )
            return False
            
        except httpx.RequestError as e:
            processing_time = time.time() - start_time
            error_msg = f"网络错误: {str(e)}"
            
            AutomationLogger.log_document_download_failed(
                document_name=document_name,
                error_message=error_msg,
                processing_time=processing_time
            )
            return False
            
        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"下载失败: {str(e)}"
            
            AutomationLogger.log_document_download_failed(
                document_name=document_name,
                error_message=error_msg,
                processing_time=processing_time
            )
            
            # 记录详细错误信息
            AutomationLogger.log_api_error_detail(
                api_name="document_download",
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc()
            )
            
            return False
