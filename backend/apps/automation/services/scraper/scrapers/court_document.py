"""
法院文书下载爬虫
支持两种链接格式：
1. https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?...
2. https://sd.gdems.com/v3/dzsd/...
"""
import logging
import os
import time
import zipfile
import json
import asyncio
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from pathlib import Path
from urllib.parse import urlparse
from django.conf import settings
from .base import BaseScraper
if TYPE_CHECKING:
    from apps.core.interfaces import ICourtDocumentService

logger = logging.getLogger("apps.automation")


# 调试模式配置（从 Django settings 读取）
from django.conf import settings
DEBUG_MODE = getattr(settings, 'DEBUG', False)  # 跟随 Django DEBUG 设置
PAUSE_ON_ERROR = False  # 设置为 True 在错误时暂停（需要手动继续）


class CourtDocumentScraper(BaseScraper):
    """
    法院文书下载爬虫
    
    根据不同的链接格式，自动选择对应的下载策略
    """
    
    def __init__(self, task, document_service: Optional["ICourtDocumentService"] = None):
        super().__init__(task)
        self.site_name = "court_document"
        self.debug_info = {}  # 存储调试信息
        self._document_service = document_service  # 文书服务（通过依赖注入）
    
    @property
    def document_service(self) -> "ICourtDocumentService":
        """
        获取文书服务实例
        
        使用延迟获取模式，支持依赖注入和默认实现
        """
        if self._document_service is None:
            from apps.core.interfaces import ServiceLocator
            self._document_service = ServiceLocator.get_court_document_service()
        return self._document_service
    
    def _debug_log(self, message: str, data: Any = None):
        """调试日志"""
        if DEBUG_MODE:
            logger.info(f"[DEBUG] {message}")
            if data:
                logger.info(f"[DEBUG] Data: {data}")
    
    def _save_debug_info(self, key: str, value: Any):
        """保存调试信息"""
        self.debug_info[key] = value
        if DEBUG_MODE:
            logger.info(f"[DEBUG] Saved {key}: {type(value)}")
    
    def _analyze_page_elements(self) -> Dict[str, Any]:
        """
        分析页面元素，用于调试
        
        Returns:
            页面元素分析结果
        """
        analysis = {
            "url": self.page.url,
            "title": self.page.title(),
            "buttons": [],
            "links": [],
            "download_elements": [],
            "iframes": [],
        }
        
        try:
            # 分析按钮
            buttons = self.page.locator("button").all()
            for i, btn in enumerate(buttons[:10]):
                try:
                    analysis["buttons"].append({
                        "index": i,
                        "text": btn.inner_text()[:50] if btn.inner_text() else "",
                        "visible": btn.is_visible(),
                    })
                except:
                    pass
            
            # 分析链接
            links = self.page.locator("a").all()
            for i, link in enumerate(links[:10]):
                try:
                    analysis["links"].append({
                        "index": i,
                        "text": link.inner_text()[:50] if link.inner_text() else "",
                        "href": link.get_attribute("href")[:100] if link.get_attribute("href") else "",
                        "visible": link.is_visible(),
                    })
                except:
                    pass
            
            # 分析包含"下载"的元素
            download_elements = self.page.locator('*:has-text("下载")').all()
            for i, elem in enumerate(download_elements[:10]):
                try:
                    tag = elem.evaluate("el => el.tagName")
                    analysis["download_elements"].append({
                        "index": i,
                        "tag": tag,
                        "text": elem.inner_text()[:50] if elem.inner_text() else "",
                        "visible": elem.is_visible(),
                    })
                except:
                    pass
            
            # 分析 iframe
            iframes = self.page.locator("iframe").all()
            for i, iframe in enumerate(iframes):
                try:
                    analysis["iframes"].append({
                        "index": i,
                        "src": iframe.get_attribute("src")[:100] if iframe.get_attribute("src") else "",
                    })
                except:
                    pass
            
        except Exception as e:
            analysis["error"] = str(e)
        
        return analysis
    
    def _save_page_state(self, name: str):
        """
        保存页面状态（截图 + HTML + 元素分析）
        
        Args:
            name: 状态名称
        """
        download_dir = self._prepare_download_dir()
        
        # 保存截图
        screenshot_path = self.screenshot(name)
        
        # 保存 HTML
        html_path = download_dir / f"{name}_page.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self.page.content())
        
        # 保存元素分析
        analysis = self._analyze_page_elements()
        analysis_path = download_dir / f"{name}_analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[DEBUG] 页面状态已保存: {name}")
        logger.info(f"  - 截图: {screenshot_path}")
        logger.info(f"  - HTML: {html_path}")
        logger.info(f"  - 分析: {analysis_path}")
        
        # 打印关键信息
        logger.info(f"  - URL: {analysis['url']}")
        logger.info(f"  - 标题: {analysis['title']}")
        logger.info(f"  - 按钮数: {len(analysis['buttons'])}")
        logger.info(f"  - 链接数: {len(analysis['links'])}")
        logger.info(f"  - 下载元素数: {len(analysis['download_elements'])}")
        logger.info(f"  - iframe数: {len(analysis['iframes'])}")
        
        return {
            "screenshot": screenshot_path,
            "html": str(html_path),
            "analysis": analysis,
        }
    
    def _intercept_api_response_with_navigation(self, timeout: int = 30000) -> Optional[Dict[str, Any]]:
        """
        在导航前注册监听器，拦截 API 响应
        
        解决原有方法的问题：API 请求在页面加载时就发出，
        但监听器在页面加载后才注册，导致错过响应。
        
        Args:
            timeout: 超时时间（毫秒），默认 30 秒
            
        Returns:
            API 响应数据字典，如果超时或失败返回 None
        """
        api_url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        intercepted_data = None
        start_time = time.time()
        
        logger.info(f"开始拦截 API 响应（导航前注册），超时时间: {timeout}ms")
        
        def handle_response(response):
            """响应处理器"""
            nonlocal intercepted_data
            
            # 检查是否是目标 API
            if api_url in response.url:
                try:
                    # 解析 JSON 响应
                    data = response.json()
                    intercepted_data = data
                    
                    # 记录统计信息
                    document_count = len(data.get('data', []))
                    response_time = (time.time() - start_time) * 1000
                    
                    logger.info(
                        f"成功拦截 API 响应",
                        extra={
                            "operation_type": "api_intercept",
                            "timestamp": time.time(),
                            "document_count": document_count,
                            "response_time_ms": response_time,
                            "api_url": api_url
                        }
                    )
                    
                except Exception as e:
                    logger.error(
                        f"解析 API 响应失败: {e}",
                        extra={
                            "operation_type": "api_intercept_parse_error",
                            "timestamp": time.time(),
                            "error": str(e),
                            "api_url": api_url
                        },
                        exc_info=True
                    )
        
        try:
            # 先注册响应监听器
            self.page.on("response", handle_response)
            logger.info(f"已注册 API 响应监听器: {api_url}")
            
            # 然后导航到目标页面
            self._debug_log("开始导航到目标页面")
            self.navigate_to_url()
            
            # 等待页面加载
            self._debug_log("等待页面加载 (networkidle)")
            self.page.wait_for_load_state("networkidle", timeout=30000)
            
            # 额外等待，确保 JS 渲染完成
            self._debug_log("额外等待 3 秒，确保页面完全加载")
            self.random_wait(3, 5)
            
            # 如果还没拦截到，再等待一段时间
            if intercepted_data is None:
                timeout_seconds = timeout / 1000.0
                elapsed = 0
                check_interval = 0.5
                
                logger.info("API 响应尚未拦截到，继续等待...")
                
                while intercepted_data is None and elapsed < timeout_seconds:
                    time.sleep(check_interval)
                    elapsed += check_interval
                
                if intercepted_data is None:
                    logger.warning(
                        f"API 拦截超时",
                        extra={
                            "operation_type": "api_intercept_timeout",
                            "timestamp": time.time(),
                            "timeout_ms": timeout,
                            "elapsed_ms": elapsed * 1000,
                            "api_url": api_url
                        }
                    )
            
        except Exception as e:
            logger.error(
                f"API 拦截过程出错: {e}",
                extra={
                    "operation_type": "api_intercept_error",
                    "timestamp": time.time(),
                    "error": str(e),
                    "api_url": api_url
                },
                exc_info=True
            )
        finally:
            # 移除监听器
            try:
                self.page.remove_listener("response", handle_response)
                logger.info("已移除 API 响应监听器")
            except Exception as e:
                logger.warning(f"移除监听器失败: {e}")
        
        return intercepted_data
    
    def _intercept_api_response(self, timeout: int = 30000) -> Optional[Dict[str, Any]]:
        """
        拦截 API 响应
        
        监听并拦截 zxfw.court.gov.cn 的文书列表 API 接口响应，
        直接获取文书下载链接和元数据。
        
        Args:
            timeout: 超时时间（毫秒），默认 30 秒
            
        Returns:
            API 响应数据字典，如果超时或失败返回 None
            
        Raises:
            无异常抛出，失败时返回 None 并记录日志
        """
        api_url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        intercepted_data = None
        start_time = time.time()
        
        logger.info(f"开始拦截 API 响应，超时时间: {timeout}ms")
        
        def handle_response(response):
            """响应处理器"""
            nonlocal intercepted_data
            
            # 检查是否是目标 API
            if api_url in response.url:
                try:
                    # 解析 JSON 响应
                    data = response.json()
                    intercepted_data = data
                    
                    # 记录统计信息
                    document_count = len(data.get('data', []))
                    response_time = (time.time() - start_time) * 1000  # 转换为毫秒
                    
                    logger.info(
                        f"成功拦截 API 响应",
                        extra={
                            "operation_type": "api_intercept",
                            "timestamp": time.time(),
                            "document_count": document_count,
                            "response_time_ms": response_time,
                            "api_url": api_url
                        }
                    )
                    
                except Exception as e:
                    logger.error(
                        f"解析 API 响应失败: {e}",
                        extra={
                            "operation_type": "api_intercept_parse_error",
                            "timestamp": time.time(),
                            "error": str(e),
                            "api_url": api_url
                        },
                        exc_info=True
                    )
        
        try:
            # 注册响应监听器
            self.page.on("response", handle_response)
            logger.info(f"已注册 API 响应监听器: {api_url}")
            
            # 等待 API 响应（使用同步方式）
            timeout_seconds = timeout / 1000.0
            elapsed = 0
            check_interval = 0.1  # 100ms 检查一次
            
            while intercepted_data is None and elapsed < timeout_seconds:
                time.sleep(check_interval)
                elapsed += check_interval
            
            # 检查是否超时
            if intercepted_data is None:
                logger.warning(
                    f"API 拦截超时",
                    extra={
                        "operation_type": "api_intercept_timeout",
                        "timestamp": time.time(),
                        "timeout_ms": timeout,
                        "elapsed_ms": elapsed * 1000,
                        "api_url": api_url
                    }
                )
            
        except Exception as e:
            logger.error(
                f"API 拦截过程出错: {e}",
                extra={
                    "operation_type": "api_intercept_error",
                    "timestamp": time.time(),
                    "error": str(e),
                    "api_url": api_url
                },
                exc_info=True
            )
        finally:
            # 移除监听器
            try:
                self.page.remove_listener("response", handle_response)
                logger.info("已移除 API 响应监听器")
            except Exception as e:
                logger.warning(f"移除监听器失败: {e}")
        
        return intercepted_data
    
    def _download_document_directly(
        self,
        document_data: Dict[str, Any],
        download_dir: Path,
        download_timeout: int = 60000
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        直接下载文书文件
        
        使用 httpx 直接下载 OSS 文件链接。
        
        Args:
            document_data: 文书数据字典，必须包含 wjlj, c_wsmc, c_wjgs 字段
            download_dir: 下载目录路径
            download_timeout: 下载超时时间（毫秒），默认 60 秒
            
        Returns:
            (成功标志, 文件路径, 错误信息) 的元组
            - 成功标志: True 表示下载成功，False 表示失败
            - 文件路径: 下载成功时返回本地文件路径，失败时返回 None
            - 错误信息: 下载失败时返回错误描述，成功时返回 None
            
        Raises:
            无异常抛出，所有错误通过返回值传递
        """
        start_time = time.time()
        
        try:
            # 提取下载 URL
            url = document_data.get('wjlj')
            if not url:
                error_msg = "文书数据中缺少下载链接 (wjlj)"
                logger.error(
                    error_msg,
                    extra={
                        "operation_type": "download_document_direct",
                        "timestamp": time.time(),
                        "document_data": document_data
                    }
                )
                return False, None, error_msg
            
            # 构建文件名（基于 c_wsmc）
            filename_base = document_data.get('c_wsmc', 'document')
            file_extension = document_data.get('c_wjgs', 'pdf')
            
            # 清理文件名中的非法字符
            import re
            filename_base = re.sub(r'[<>:"/\\|?*]', '_', filename_base)
            filename = f"{filename_base}.{file_extension}"
            
            filepath = download_dir / filename
            
            logger.info(
                f"开始直接下载文书",
                extra={
                    "operation_type": "download_document_direct_start",
                    "timestamp": time.time(),
                    "url": url,
                    "file_name": filename,
                    "timeout_ms": download_timeout
                }
            )
            
            # 使用 httpx 下载文件
            try:
                import httpx
                
                timeout_seconds = download_timeout / 1000.0
                
                with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    
                    # 保存文件
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                
                # 获取文件大小
                file_size = filepath.stat().st_size
                download_time = (time.time() - start_time) * 1000  # 转换为毫秒
                
                logger.info(
                    f"文书下载成功",
                    extra={
                        "operation_type": "download_document_direct_success",
                        "timestamp": time.time(),
                        "file_name": filename,
                        "file_size": file_size,
                        "download_time_ms": download_time,
                        "file_path": str(filepath)
                    }
                )
                
                return True, str(filepath), None
                
            except Exception as e:
                error_msg = f"下载失败: {str(e)}"
                download_time = (time.time() - start_time) * 1000
                
                logger.error(
                    error_msg,
                    extra={
                        "operation_type": "download_document_direct_failed",
                        "timestamp": time.time(),
                        "url": url,
                        "file_name": filename,
                        "download_time_ms": download_time,
                        "error": str(e)
                    },
                    exc_info=True
                )
                
                return False, None, error_msg
                
        except Exception as e:
            error_msg = f"处理下载请求失败: {str(e)}"
            logger.error(
                error_msg,
                extra={
                    "operation_type": "download_document_direct_error",
                    "timestamp": time.time(),
                    "document_data": document_data
                },
                exc_info=True
            )
            return False, None, error_msg
    
    def _try_click_download(self, timeout: int = 30000) -> Optional[Any]:
        """
        尝试多种方式点击下载按钮
        
        Args:
            timeout: 超时时间（毫秒）
            
        Returns:
            下载对象，如果失败返回 None
        """
        strategies = [
            # 策略 1: ID 选择器
            {"name": "ID #download", "locator": "#download"},
            # 策略 2: 文本匹配
            {"name": "文本 '下载'", "locator": "text=下载"},
            # 策略 3: 按钮角色
            {"name": "按钮角色", "locator": "button:has-text('下载')"},
            # 策略 4: 链接
            {"name": "链接", "locator": "a:has-text('下载')"},
            # 策略 5: 任意可点击元素
            {"name": "可点击元素", "locator": "[onclick*='download'], [href*='download']"},
        ]
        
        for strategy in strategies:
            try:
                logger.info(f"[DEBUG] 尝试策略: {strategy['name']}")
                
                locator = self.page.locator(strategy["locator"]).first
                if locator.count() == 0:
                    logger.info(f"[DEBUG] 策略 {strategy['name']}: 未找到元素")
                    continue
                
                if not locator.is_visible():
                    logger.info(f"[DEBUG] 策略 {strategy['name']}: 元素不可见")
                    continue
                
                logger.info(f"[DEBUG] 策略 {strategy['name']}: 找到元素，尝试点击")
                
                # 滚动到元素
                locator.scroll_into_view_if_needed()
                self.random_wait(0.5, 1)
                
                # 尝试下载
                with self.page.expect_download(timeout=timeout) as download_info:
                    locator.click()
                    logger.info(f"[DEBUG] 策略 {strategy['name']}: 点击成功，等待下载")
                
                download = download_info.value
                logger.info(f"[DEBUG] 策略 {strategy['name']}: 下载成功！文件: {download.suggested_filename}")
                return download
                
            except Exception as e:
                logger.warning(f"[DEBUG] 策略 {strategy['name']} 失败: {e}")
                continue
        
        return None
    
    def _run(self) -> Dict[str, Any]:
        """
        执行文书下载任务
        
        Returns:
            包含下载文件路径列表的字典
        """
        logger.info(f"执行法院文书下载: {self.task.url}")
        
        # 根据 URL 判断链接类型
        url = self.task.url
        
        if "zxfw.court.gov.cn" in url:
            return self._download_zxfw_court(url)
        elif "sd.gdems.com" in url:
            return self._download_gdems(url)
        else:
            raise ValueError(f"不支持的链接格式: {url}")
    
    def _download_zxfw_court(self, url: str) -> Dict[str, Any]:
        """
        下载 zxfw.court.gov.cn 的文书
        
        三级下载策略：
        1. 优先：直接调用 API（无需浏览器，速度最快）
        2. 次选：Playwright 拦截 API 响应
        3. 回退：传统页面点击下载
        
        Args:
            url: 文书链接
            
        Returns:
            下载结果字典
        """
        logger.info("=" * 60)
        logger.info("处理 zxfw.court.gov.cn 链接...")
        logger.info("=" * 60)
        
        # 准备下载目录
        download_dir = self._prepare_download_dir()
        
        # ========== 第一优先级：直接调用 API ==========
        direct_api_error = None
        try:
            logger.info(
                "尝试直接调用 API 获取文书列表（无需浏览器）",
                extra={
                    "operation_type": "direct_api_attempt",
                    "timestamp": time.time(),
                    "url": url
                }
            )
            
            result = self._download_via_direct_api(url, download_dir)
            
            logger.info(
                "直接 API 调用成功",
                extra={
                    "operation_type": "direct_api_success",
                    "timestamp": time.time(),
                    "document_count": result.get("document_count", 0),
                    "downloaded_count": result.get("downloaded_count", 0)
                }
            )
            
            return result
            
        except Exception as e:
            direct_api_error = e
            logger.warning(
                f"直接 API 调用失败，尝试 Playwright 拦截方式",
                extra={
                    "operation_type": "direct_api_failed",
                    "timestamp": time.time(),
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
        
        # ========== 第二优先级：Playwright 拦截 API ==========
        api_intercept_error = None
        try:
            logger.info(
                "尝试使用 Playwright API 拦截方式",
                extra={
                    "operation_type": "api_intercept_attempt",
                    "timestamp": time.time(),
                    "url": url
                }
            )
            
            result = self._download_via_api_intercept_with_navigation(download_dir)
            result["method"] = "api_intercept"
            result["direct_api_error"] = {
                "type": type(direct_api_error).__name__,
                "message": str(direct_api_error)
            }
            
            logger.info(
                "Playwright API 拦截成功",
                extra={
                    "operation_type": "api_intercept_success",
                    "timestamp": time.time(),
                    "document_count": result.get("document_count", 0),
                    "downloaded_count": result.get("downloaded_count", 0)
                }
            )
            
            return result
            
        except Exception as e:
            api_intercept_error = e
            logger.warning(
                f"Playwright API 拦截失败，回退到传统方式",
                extra={
                    "operation_type": "api_intercept_failed",
                    "timestamp": time.time(),
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
        
        # ========== 第三优先级：传统页面点击 ==========
        try:
            logger.info(
                "使用回退机制：传统页面点击下载",
                extra={
                    "operation_type": "fallback_attempt",
                    "timestamp": time.time()
                }
            )
            
            result = self._download_via_fallback(download_dir)
            result["method"] = "fallback"
            result["direct_api_error"] = {
                "type": type(direct_api_error).__name__,
                "message": str(direct_api_error)
            }
            result["api_intercept_error"] = {
                "type": type(api_intercept_error).__name__,
                "message": str(api_intercept_error)
            }
            
            logger.info(
                "回退机制执行成功",
                extra={
                    "operation_type": "fallback_success",
                    "timestamp": time.time(),
                    "downloaded_count": result.get("downloaded_count", 0)
                }
            )
            
            return result
            
        except Exception as fallback_error:
            logger.error(
                "所有下载方式均失败",
                extra={
                    "operation_type": "all_methods_failed",
                    "timestamp": time.time(),
                    "direct_api_error": str(direct_api_error),
                    "api_intercept_error": str(api_intercept_error),
                    "fallback_error": str(fallback_error)
                },
                exc_info=True
            )
            
            from apps.core.exceptions import ExternalServiceError
            
            raise ExternalServiceError(
                message="所有下载方式均失败",
                code="DOWNLOAD_ALL_METHODS_FAILED",
                errors={
                    "direct_api_error": str(direct_api_error),
                    "api_intercept_error": str(api_intercept_error),
                    "fallback_error": str(fallback_error)
                }
            )
    
    def _extract_url_params(self, url: str) -> Optional[Dict[str, str]]:
        """
        从 URL 中提取 sdbh, qdbh, sdsin 参数
        
        Args:
            url: 法院文书链接
            
        Returns:
            参数字典，如果提取失败返回 None
        """
        from urllib.parse import urlparse, parse_qs
        
        try:
            parsed_url = urlparse(url)
            # 参数可能在 query 或 fragment 中
            query_part = parsed_url.query if parsed_url.query else parsed_url.fragment
            if '?' in query_part:
                query_part = query_part.split('?', 1)[1]
            
            params = parse_qs(query_part)
            sdbh = params.get('sdbh', [None])[0]
            qdbh = params.get('qdbh', [None])[0]
            sdsin = params.get('sdsin', [None])[0]
            
            if sdbh and qdbh and sdsin:
                logger.info(f"提取 URL 参数成功: sdbh={sdbh}, qdbh={qdbh}, sdsin={sdsin}")
                return {"sdbh": sdbh, "qdbh": qdbh, "sdsin": sdsin}
            else:
                logger.warning(f"URL 参数不完整: sdbh={sdbh}, qdbh={qdbh}, sdsin={sdsin}")
                return None
        except Exception as e:
            logger.error(f"解析 URL 参数失败: {e}")
            return None
    
    def _fetch_documents_via_direct_api(self, params: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        直接调用法院 API 获取文书列表（无需浏览器）
        
        Args:
            params: 包含 sdbh, qdbh, sdsin 的参数字典
            
        Returns:
            文书列表
            
        Raises:
            Exception: API 调用失败时抛出异常
        """
        import httpx
        
        api_url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'DNT': '1',
            'Origin': 'https://zxfw.court.gov.cn',
            'Referer': 'https://zxfw.court.gov.cn/zxfw/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
        }
        
        payload = {
            "sdbh": params.get("sdbh"),
            "qdbh": params.get("qdbh"),
            "sdsin": params.get("sdsin")
        }
        
        logger.info(f"直接调用 API: {api_url}, payload: {payload}")
        
        start_time = time.time()
        
        with httpx.Client(headers=headers, timeout=30.0) as client:
            response = client.post(api_url, json=payload)
            response.raise_for_status()
            
            api_data = response.json()
            response_time = (time.time() - start_time) * 1000
            
            logger.info(
                f"API 响应成功",
                extra={
                    "operation_type": "direct_api_response",
                    "timestamp": time.time(),
                    "status_code": response.status_code,
                    "response_time_ms": response_time
                }
            )
        
        # 验证响应格式
        if not isinstance(api_data, dict) or api_data.get('code') != 200:
            raise ValueError(f"API 响应错误: code={api_data.get('code')}, msg={api_data.get('msg')}")
        
        documents = api_data.get('data', [])
        if not isinstance(documents, list):
            raise ValueError(f"API 响应 data 字段格式错误: {type(documents)}")
        
        logger.info(f"直接 API 获取到 {len(documents)} 个文书")
        return documents
    
    def _download_via_direct_api(self, url: str, download_dir: Path) -> Dict[str, Any]:
        """
        通过直接调用 API 下载文书（无需浏览器，速度最快）
        
        Args:
            url: 文书链接
            download_dir: 下载目录
            
        Returns:
            下载结果字典
            
        Raises:
            Exception: 参数提取或 API 调用失败时抛出异常
        """
        # 1. 从 URL 提取参数
        params = self._extract_url_params(url)
        if not params:
            raise ValueError("无法从 URL 中提取必要参数 (sdbh, qdbh, sdsin)")
        
        # 2. 直接调用 API 获取文书列表
        documents = self._fetch_documents_via_direct_api(params)
        
        if len(documents) == 0:
            raise ValueError("API 返回的文书列表为空")
        
        logger.info(f"直接 API 获取到 {len(documents)} 个文书，开始下载")
        
        # 3. 下载所有文书
        downloaded_files = []
        documents_with_results = []
        success_count = 0
        failed_count = 0
        
        for i, document_data in enumerate(documents, 1):
            logger.info(f"下载第 {i}/{len(documents)} 个文书: {document_data.get('c_wsmc', 'Unknown')}")
            
            download_result = self._download_document_directly(
                document_data=document_data,
                download_dir=download_dir,
                download_timeout=60000
            )
            
            success, filepath, error = download_result
            
            if success:
                success_count += 1
                downloaded_files.append(filepath)
            else:
                failed_count += 1
            
            documents_with_results.append((document_data, download_result))
            
            # 下载延迟
            if i < len(documents):
                import random
                delay = random.uniform(0.5, 1.5)
                time.sleep(delay)
        
        # 4. 批量保存到数据库
        db_save_result = self._save_documents_batch(documents_with_results)
        
        logger.info(
            f"直接 API 方式下载完成",
            extra={
                "operation_type": "direct_api_download_summary",
                "timestamp": time.time(),
                "total_count": len(documents),
                "success_count": success_count,
                "failed_count": failed_count
            }
        )
        
        return {
            "source": "zxfw.court.gov.cn",
            "method": "direct_api",
            "document_count": len(documents),
            "downloaded_count": success_count,
            "failed_count": failed_count,
            "files": downloaded_files,
            "db_save_result": db_save_result,
            "message": f"直接 API 方式：成功下载 {success_count}/{len(documents)} 份文书"
        }
    
    def _download_via_api_intercept_with_navigation(self, download_dir: Path) -> Dict[str, Any]:
        """
        通过 API 拦截方式下载文书（在导航前注册监听器）
        
        解决原有方法的问题：API 请求在页面加载时就发出，
        但监听器在页面加载后才注册，导致错过响应。
        
        Args:
            download_dir: 下载目录
            
        Returns:
            下载结果字典
            
        Raises:
            Exception: API 拦截或下载失败时抛出异常
        """
        # 在导航前注册监听器并拦截 API 响应
        api_data = self._intercept_api_response_with_navigation(timeout=30000)
        
        # 保存页面状态（用于调试）
        self._debug_log("保存页面状态")
        self._save_page_state("zxfw_after_navigation")
        
        return self._process_api_data_and_download(api_data, download_dir)
    
    def _download_via_api_intercept(self, download_dir: Path) -> Dict[str, Any]:
        """
        通过 API 拦截方式下载文书（已废弃，保留用于回退）
        
        注意：此方法在页面加载后才注册监听器，可能错过 API 响应。
        推荐使用 _download_via_api_intercept_with_navigation
        
        Args:
            download_dir: 下载目录
            
        Returns:
            下载结果字典
            
        Raises:
            Exception: API 拦截或下载失败时抛出异常
        """
        # 拦截 API 响应
        api_data = self._intercept_api_response(timeout=30000)
        
        return self._process_api_data_and_download(api_data, download_dir)
    
    def _process_api_data_and_download(self, api_data: Optional[Dict[str, Any]], download_dir: Path) -> Dict[str, Any]:
        """
        处理 API 数据并下载文书
        
        Args:
            api_data: API 响应数据
            download_dir: 下载目录
            
        Returns:
            下载结果字典
        """
        
        if api_data is None:
            raise ValueError("API 拦截超时，未能获取文书列表")
        
        # 验证响应格式
        if not isinstance(api_data, dict):
            raise ValueError(f"API 响应格式错误：期望 dict，实际 {type(api_data)}")
        
        if "data" not in api_data:
            raise ValueError("API 响应缺少 data 字段")
        
        documents = api_data.get("data", [])
        if not isinstance(documents, list):
            raise ValueError(f"API 响应 data 字段格式错误：期望 list，实际 {type(documents)}")
        
        if len(documents) == 0:
            raise ValueError("API 响应中没有文书数据")
        
        logger.info(
            f"成功获取文书列表，共 {len(documents)} 个文书",
            extra={
                "operation_type": "api_intercept_parse_success",
                "timestamp": time.time(),
                "document_count": len(documents)
            }
        )
        
        # 下载所有文书
        downloaded_files = []
        documents_with_results = []
        success_count = 0
        failed_count = 0
        
        for i, document_data in enumerate(documents, 1):
            logger.info(f"处理第 {i}/{len(documents)} 个文书: {document_data.get('c_wsmc', 'Unknown')}")
            
            # 下载文书
            download_result = self._download_document_directly(
                document_data=document_data,
                download_dir=download_dir,
                download_timeout=60000
            )
            
            success, filepath, error = download_result
            
            if success:
                success_count += 1
                downloaded_files.append(filepath)
            else:
                failed_count += 1
            
            # 保存文书数据和下载结果，用于后续数据库保存
            documents_with_results.append((document_data, download_result))
            
            # 添加下载延迟（避免触发反爬机制）
            if i < len(documents):
                import random
                delay = random.uniform(1, 2)
                logger.info(f"等待 {delay:.2f} 秒后继续下载下一个文书")
                time.sleep(delay)
        
        # 批量保存到数据库
        db_save_result = self._save_documents_batch(documents_with_results)
        
        # 记录汇总日志
        logger.info(
            f"文书下载完成",
            extra={
                "operation_type": "download_summary",
                "timestamp": time.time(),
                "total_count": len(documents),
                "success_count": success_count,
                "failed_count": failed_count,
                "db_saved_count": db_save_result.get("success", 0),
                "db_failed_count": db_save_result.get("failed", 0)
            }
        )
        
        return {
            "source": "zxfw.court.gov.cn",
            "method": "api_intercept",
            "document_count": len(documents),
            "downloaded_count": success_count,
            "failed_count": failed_count,
            "files": downloaded_files,
            "db_save_result": db_save_result,
            "message": f"API 拦截方式：成功下载 {success_count}/{len(documents)} 份文书"
        }
    
    def _download_via_fallback(self, download_dir: Path) -> Dict[str, Any]:
        """
        通过传统页面点击方式下载文书（回退机制）
        
        Args:
            download_dir: 下载目录
            
        Returns:
            下载结果字典
            
        Raises:
            Exception: 下载失败时抛出异常
        """
        downloaded_files = []
        success_count = 0
        failed_count = 0
        
        # 检测文书列表数量
        # 文书列表容器 XPath
        doc_list_xpath = "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view/uni-view[1]/uni-view[1]/uni-view"
        
        try:
            doc_items = self.page.locator(f"xpath={doc_list_xpath}").all()
            doc_count = len(doc_items)
            logger.info(f"[DEBUG] 检测到 {doc_count} 个文书项")
        except Exception as e:
            logger.warning(f"[DEBUG] 无法检测文书列表: {e}，尝试单文件下载")
            doc_count = 1
        
        if doc_count == 0:
            # 没有检测到文书列表，尝试直接下载
            logger.info("[DEBUG] 未检测到文书列表，尝试直接下载")
            doc_count = 1
        
        # 逐一下载每个文书
        for doc_index in range(1, doc_count + 1):
            logger.info(f"\n{'='*40}")
            logger.info(f"[DEBUG] 下载第 {doc_index}/{doc_count} 个文书")
            logger.info(f"{'='*40}")
            
            try:
                # 如果有多个文书，需要先点击对应的文书项
                if doc_count > 1 or doc_index > 1:
                    # 点击文书项
                    doc_item_xpath = f"/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view/uni-view[1]/uni-view[1]/uni-view[{doc_index}]"
                    
                    try:
                        doc_item = self.page.locator(f"xpath={doc_item_xpath}")
                        if doc_item.count() > 0:
                            doc_item.first.click()
                            logger.info(f"[DEBUG] 已点击第 {doc_index} 个文书项")
                            self.random_wait(2, 3)  # 等待 PDF 加载
                        else:
                            logger.warning(f"[DEBUG] 未找到第 {doc_index} 个文书项")
                    except Exception as e:
                        logger.warning(f"[DEBUG] 点击文书项失败: {e}")
                
                # 查找 iframe（使用 ID #if）
                frame = None
                try:
                    # 优先使用 ID 选择器
                    frame = self.page.frame_locator("#if")
                    logger.info("[DEBUG] 通过 #if 找到 iframe")
                except Exception:
                    pass
                
                if not frame:
                    # 备用：查找包含 pdfjs 的 iframe
                    iframes = self.page.locator("iframe").all()
                    for i, iframe in enumerate(iframes):
                        src = iframe.get_attribute("src") or ""
                        iframe_id = iframe.get_attribute("id") or ""
                        logger.info(f"[DEBUG] 检查 iframe {i}: id={iframe_id}, src={src[:60]}...")
                        
                        if iframe_id == "if" or "pdfjs" in src or "viewer" in src:
                            frame = self.page.frame_locator(f"iframe >> nth={i}")
                            logger.info(f"[DEBUG] 找到 PDF viewer iframe (index {i})")
                            break
                
                if not frame:
                    logger.warning(f"[DEBUG] 第 {doc_index} 个文书未找到 iframe，跳过")
                    continue
                
                # 在 iframe 内点击下载按钮
                try:
                    # 使用 #download ID
                    btn = frame.locator("#download")
                    btn.first.wait_for(state="visible", timeout=10000)
                    btn.first.scroll_into_view_if_needed()
                    self.random_wait(1, 2)
                    
                    # 监听下载
                    with self.page.expect_download(timeout=60000) as download_info:
                        btn.first.click()
                        logger.info(f"[DEBUG] 已点击第 {doc_index} 个文书的下载按钮")
                    
                    download = download_info.value
                    
                    # 保存文件
                    filename = download.suggested_filename or f"document_{doc_index}.pdf"
                    filepath = download_dir / filename
                    download.save_as(str(filepath))
                    logger.info(f"[DEBUG] 文件已保存: {filepath}")
                    downloaded_files.append(str(filepath))
                    success_count += 1
                    
                except Exception as e:
                    logger.warning(f"[DEBUG] #download 方式失败: {e}，尝试备用 XPath")
                    
                    # 备用：使用原来的 XPath
                    try:
                        download_xpath = "/html/body/div[1]/div[2]/div[5]/div/div[1]/div[2]/button[4]"
                        btn = frame.locator(f"xpath={download_xpath}")
                        btn.first.wait_for(state="visible", timeout=5000)
                        
                        with self.page.expect_download(timeout=60000) as download_info:
                            btn.first.click()
                            logger.info(f"[DEBUG] 通过备用 XPath 点击下载按钮")
                        
                        download = download_info.value
                        filename = download.suggested_filename or f"document_{doc_index}.pdf"
                        filepath = download_dir / filename
                        download.save_as(str(filepath))
                        downloaded_files.append(str(filepath))
                        success_count += 1
                        
                    except Exception as e2:
                        logger.error(f"[DEBUG] 第 {doc_index} 个文书下载失败: {e2}")
                        failed_count += 1
                
                # 下载完成后等待一下
                self.random_wait(1, 2)
                
            except Exception as e:
                logger.error(f"[DEBUG] 处理第 {doc_index} 个文书时出错: {e}")
                failed_count += 1
                continue
        
        if not downloaded_files:
            # 最终失败，保存详细调试信息
            self._save_page_state("zxfw_final_failed")
            raise ValueError("所有下载策略均失败，请查看调试文件")
        
        # 记录汇总日志
        logger.info(
            f"回退方式下载完成",
            extra={
                "operation_type": "fallback_download_summary",
                "timestamp": time.time(),
                "total_count": doc_count,
                "success_count": success_count,
                "failed_count": failed_count
            }
        )
        
        return {
            "source": "zxfw.court.gov.cn",
            "document_count": doc_count,
            "downloaded_count": success_count,
            "failed_count": failed_count,
            "files": downloaded_files,
            "message": f"回退方式：成功下载 {success_count}/{doc_count} 份文书"
        }
    
    def _download_gdems(self, url: str) -> Dict[str, Any]:
        """
        下载 sd.gdems.com 的文书
        
        特点：
        - 先进入封面页
        - 需要点击"确认并预览材料"按钮
        - 然后通过 XPath /html/body/div/div[1]/div[1]/label/a/img 下载压缩包
        
        Args:
            url: 文书链接
            
        Returns:
            下载结果
        """
        logger.info("=" * 60)
        logger.info("处理 sd.gdems.com 链接...")
        logger.info("=" * 60)
        
        # 导航到目标页面
        self.navigate_to_url()
        
        # 等待页面加载
        self.page.wait_for_load_state("networkidle", timeout=30000)
        self.random_wait(3, 5)
        
        # 截图保存封面页
        screenshot_cover = self.screenshot("gdems_cover")
        
        # 点击"确认并预览材料"按钮
        try:
            submit_button = None
            
            # 方案 1: 使用 ID/class
            try:
                submit_button = self.page.locator("#submit-btn, #confirm-btn, .submit-btn, .confirm-btn")
                if submit_button.count() > 0 and submit_button.first.is_visible():
                    logger.info("通过 ID/class 找到确认按钮")
                else:
                    submit_button = None
            except:
                pass
            
            # 方案 2: 使用文本
            if not submit_button:
                try:
                    submit_button = self.page.get_by_text("确认并预览材料", exact=False)
                    if submit_button.count() > 0 and submit_button.first.is_visible():
                        logger.info("通过文本找到确认按钮")
                    else:
                        submit_button = None
                except:
                    pass
            
            # 方案 3: 使用按钮文本
            if not submit_button:
                try:
                    submit_button = self.page.locator("button:has-text('确认'), button:has-text('确定'), button:has-text('预览')")
                    if submit_button.count() > 0 and submit_button.first.is_visible():
                        logger.info("通过按钮选择器找到确认按钮")
                    else:
                        submit_button = None
                except:
                    pass
            
            if submit_button and submit_button.count() > 0:
                submit_button.first.click()
                logger.info("已点击'确认并预览材料'按钮")
                
                # 等待预览页加载
                self.page.wait_for_load_state("networkidle", timeout=30000)
                self.random_wait(5, 7)
            else:
                logger.warning("未找到确认按钮，可能页面已经在预览状态")
            
        except Exception as e:
            logger.warning(f"点击确认按钮时出错: {e}，继续尝试下载")
        
        # 截图保存预览页
        screenshot_preview = self.screenshot("gdems_preview")
        
        # 准备下载目录
        download_dir = self._prepare_download_dir()
        
        # 点击下载按钮 - 多种方式尝试
        download_xpath = "/html/body/div/div[1]/div[1]/label/a/img"
        
        try:
            download_button = None
            
            # 方式1: 使用 downloadPackClass 类名（最可靠）
            try:
                download_button = self.page.locator("a.downloadPackClass")
                if download_button.count() > 0 and download_button.first.is_visible():
                    logger.info("通过 a.downloadPackClass 找到下载按钮")
                else:
                    download_button = None
            except:
                pass
            
            # 方式2: 使用提供的 XPath
            if not download_button:
                try:
                    download_button = self.page.locator(f"xpath={download_xpath}")
                    if download_button.count() > 0 and download_button.first.is_visible():
                        logger.info(f"通过 XPath 找到下载按钮: {download_xpath}")
                    else:
                        download_button = None
                except:
                    pass
            
            # 方式3: 查找 label 下的 a 标签（包含 img）
            if not download_button:
                try:
                    download_button = self.page.locator("label a:has(img)")
                    if download_button.count() > 0 and download_button.first.is_visible():
                        logger.info("通过 label a:has(img) 找到下载按钮")
                    else:
                        download_button = None
                except:
                    pass
            
            # 方式4: 查找包含"送达材料"文本的链接
            if not download_button:
                try:
                    download_button = self.page.locator("a:has-text('送达材料')")
                    if download_button.count() > 0 and download_button.first.is_visible():
                        logger.info("通过文本'送达材料'找到下载按钮")
                    else:
                        download_button = None
                except:
                    pass
            
            # 方式5: 查找任何包含"下载"的元素
            if not download_button:
                try:
                    download_button = self.page.locator("a:has-text('下载'), button:has-text('下载'), [title*='下载']")
                    if download_button.count() > 0 and download_button.first.is_visible():
                        logger.info("通过文本找到下载按钮")
                    else:
                        download_button = None
                except:
                    pass
            
            if not download_button or download_button.count() == 0:
                # 保存页面 HTML 用于调试
                self._save_page_state("gdems_no_download_button")
                raise ValueError("找不到下载按钮")
            
            # 滚动到按钮位置
            download_button.first.scroll_into_view_if_needed()
            self.random_wait(1, 2)
            
            # 监听下载事件
            with self.page.expect_download(timeout=60000) as download_info:
                download_button.first.click()
                logger.info("已点击下载按钮，等待下载...")
            
            download = download_info.value
            
            # 保存 ZIP 文件
            zip_filename = download.suggested_filename or "documents.zip"
            zip_filepath = download_dir / zip_filename
            download.save_as(str(zip_filepath))
            
            logger.info(f"ZIP 文件已保存: {zip_filepath}")
            
        except Exception as e:
            logger.error(f"下载失败: {e}")
            self._save_page_state("gdems_download_error")
            raise ValueError(f"文件下载失败: {e}")
        
        # 解压 ZIP 文件
        extracted_files = []
        try:
            extract_dir = download_dir / "extracted"
            extract_dir.mkdir(exist_ok=True)
            
            with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
                extracted_files = [str(extract_dir / name) for name in zip_ref.namelist()]
            
            logger.info(f"ZIP 文件已解压，共 {len(extracted_files)} 个文件")
            
        except Exception as e:
            logger.error(f"解压失败: {e}")
            # 解压失败不影响主流程，返回 ZIP 文件
            extracted_files = []
        
        # 构建文件列表（用于结果显示）
        all_files = [str(zip_filepath)] + extracted_files
        
        return {
            "source": "sd.gdems.com",
            "zip_file": str(zip_filepath),
            "extracted_files": extracted_files,
            "files": all_files,  # 添加 files 字段，与 zxfw 保持一致
            "file_count": len(extracted_files),
            "screenshots": [screenshot_cover, screenshot_preview],
            "message": f"成功下载并解压 {len(extracted_files)} 个文件"
        }
    
    def _prepare_download_dir(self) -> Path:
        """
        准备下载目录
        
        Returns:
            下载目录路径
        """
        # 如果任务关联了案件，使用案件 ID 作为目录名
        if self.task.case_id:
            download_dir = Path(settings.MEDIA_ROOT) / "case_logs" / str(self.task.case_id) / "documents"
        else:
            download_dir = Path(settings.MEDIA_ROOT) / "automation" / "downloads" / f"task_{self.task.id}"
        
        download_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"下载目录: {download_dir}")
        
        return download_dir
    
    def _save_document_to_db(
        self,
        document_data: Dict[str, Any],
        download_result: tuple[bool, Optional[str], Optional[str]]
    ) -> Optional[int]:
        """
        保存单个文书记录到数据库
        
        此方法不会抛出异常，所有错误都会被捕获并记录，
        确保数据库保存失败不会阻断下载流程。
        
        Args:
            document_data: 文书数据字典，包含 API 返回的所有字段
            download_result: 下载结果元组 (成功标志, 文件路径, 错误信息)
            
        Returns:
            创建的文书记录 ID，失败时返回 None
            
        Raises:
            无异常抛出，所有错误通过日志记录
        """
        try:
            success, filepath, error = download_result
            
            # 先创建文书记录
            document = self.document_service.create_document_from_api_data(
                scraper_task_id=self.task.id,
                api_data=document_data,
                case_id=self.task.case_id
            )
            
            # 根据下载结果更新状态
            if success:
                # 获取文件大小
                file_size = None
                if filepath:
                    try:
                        file_size = Path(filepath).stat().st_size
                    except Exception as e:
                        logger.warning(f"无法获取文件大小: {e}")
                
                # 更新为成功状态
                document = self.document_service.update_download_status(
                    document_id=document.id,
                    status="success",
                    local_file_path=filepath,
                    file_size=file_size
                )
            else:
                # 更新为失败状态
                document = self.document_service.update_download_status(
                    document_id=document.id,
                    status="failed",
                    error_message=error
                )
            
            logger.info(
                f"文书记录已保存到数据库",
                extra={
                    "operation_type": "save_document_to_db",
                    "timestamp": time.time(),
                    "document_id": document.id,
                    "c_wsmc": document.c_wsmc,
                    "download_status": document.download_status,
                    "file_path": filepath
                }
            )
            
            return document.id
            
        except Exception as e:
            # 捕获所有异常，记录详细日志，但不抛出
            logger.error(
                f"保存文书记录到数据库失败: {e}",
                extra={
                    "operation_type": "save_document_to_db_error",
                    "timestamp": time.time(),
                    "document_data": document_data,
                    "download_result": download_result,
                    "error": str(e)
                },
                exc_info=True
            )
            return None
    
    def _save_documents_batch(
        self,
        documents_with_results: List[tuple[Dict[str, Any], tuple[bool, Optional[str], Optional[str]]]]
    ) -> Dict[str, Any]:
        """
        批量保存文书记录到数据库
        
        使用批量创建优化性能，同时确保单个失败不影响其他记录。
        
        Args:
            documents_with_results: 文书数据和下载结果的列表
                每个元素是 (document_data, download_result) 元组
                
        Returns:
            保存结果统计字典，包含：
            - total: 总数
            - success: 成功保存的数量
            - failed: 失败的数量
            - document_ids: 成功保存的文书 ID 列表
            
        Raises:
            无异常抛出，所有错误通过日志记录
        """
        start_time = time.time()
        total = len(documents_with_results)
        success_count = 0
        failed_count = 0
        document_ids = []
        
        logger.info(
            f"开始批量保存文书记录",
            extra={
                "operation_type": "save_documents_batch_start",
                "timestamp": time.time(),
                "total_count": total
            }
        )
        
        # 逐个保存（确保错误隔离）
        for document_data, download_result in documents_with_results:
            document_id = self._save_document_to_db(document_data, download_result)
            
            if document_id is not None:
                success_count += 1
                document_ids.append(document_id)
            else:
                failed_count += 1
        
        elapsed_time = (time.time() - start_time) * 1000  # 转换为毫秒
        
        logger.info(
            f"批量保存文书记录完成",
            extra={
                "operation_type": "save_documents_batch_complete",
                "timestamp": time.time(),
                "total_count": total,
                "success_count": success_count,
                "failed_count": failed_count,
                "elapsed_time_ms": elapsed_time
            }
        )
        
        return {
            "total": total,
            "success": success_count,
            "failed": failed_count,
            "document_ids": document_ids
        }
