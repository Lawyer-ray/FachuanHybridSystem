"""
全国法院"一张网"服务 (zxfw.court.gov.cn)
提供登录、立案、查询等功能
"""

import logging
import socket
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from playwright.sync_api import BrowserContext
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

if TYPE_CHECKING:
    from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognizer
    from apps.automation.services.scraper.core.token_service import TokenService


class CookieServiceProtocol(Protocol):
    """Cookie 服务协议，支持依赖注入"""

    def load(self, context: Any, storage_path: str | None = None) -> bool:
        """加载 Cookie 到浏览器上下文，返回是否成功"""
        ...

    def save(self, context: Any, storage_path: str | None = None) -> str:
        """保存浏览器上下文中的 Cookie，返回存储路径"""
        ...


logger = logging.getLogger("apps.automation")


class CourtZxfwService:
    """
    全国法院"一张网"服务 - 支持依赖注入

    功能模块化设计：
    - login(): 登录
    - file_case(): 立案
    - query_case(): 查询案件
    - download_document(): 下载文书

    依赖注入：
    - captcha_recognizer: 验证码识别器（可选）
    - token_service: Token 服务（可选）
    """

    BASE_URL = "https://zxfw.court.gov.cn/zxfw"
    LOGIN_URL = f"{BASE_URL}/#/pagesGrxx/pc/login/index"

    def __init__(
        self,
        page: Page,
        context: BrowserContext,
        captcha_recognizer: "CaptchaRecognizer | None" = None,
        token_service: "TokenService | None" = None,
        site_name: str = "court_zxfw",
        cookie_service: CookieServiceProtocol | None = None,
    ):
        """
        初始化服务

        Args:
            page: Playwright Page 对象
            context: Playwright BrowserContext 对象
            captcha_recognizer: 验证码识别器，None 则使用默认的 DdddocrRecognizer
            token_service: Token 服务，None 则使用默认的 TokenService
            site_name: 网站名称，用于 Token 管理，默认 "court_zxfw"
            cookie_service: Cookie 服务，None 则不使用 Cookie 管理
        """
        self.page = page
        self.context = context
        self.site_name = site_name
        self.is_logged_in = False

        # 依赖注入：Cookie 服务
        if cookie_service is None:
            from apps.automation.services.scraper.core.cookie_service import CookieService

            self._cookie_service: CookieServiceProtocol = CookieService()
        else:
            self._cookie_service = cookie_service

        # 依赖注入：验证码识别器
        if captcha_recognizer is None:
            from apps.automation.services.scraper.core.captcha_recognizer import DdddocrRecognizer

            self.captcha_recognizer = DdddocrRecognizer(show_ad=False)
            logger.info("使用默认的 DdddocrRecognizer")
        else:
            self.captcha_recognizer = captcha_recognizer
            logger.info(f"使用注入的验证码识别器: {type(captcha_recognizer).__name__}")

        # 依赖注入：Token 服务（延迟加载）
        self._token_service = token_service
        if token_service is not None:
            logger.info(f"使用注入的 Token 服务: {type(token_service).__name__}")

    @property
    def cookie_service(self) -> Any:
        """获取 Cookie 服务"""
        return self._cookie_service

    @property
    def token_service(self) -> Any:
        """获取 Token 服务（延迟加载）"""
        if self._token_service is None:
            from apps.core.interfaces import ServiceLocator

            self._token_service = ServiceLocator.get_token_service()
            logger.info("使用 ServiceLocator 获取 TokenService")
        return self._token_service

    def _extract_token_from_body(self, body: dict[str, Any]) -> str | None:
        """从响应体中提取 token，尝试多个字段路径"""
        token_keys = ("token", "access_token", "accessToken")
        for wrapper in ("data", "result"):
            if wrapper in body and isinstance(body[wrapper], dict):
                for key in token_keys:
                    if body[wrapper].get(key):
                        return str(body[wrapper][key])
        for key in token_keys:
            if body.get(key):
                return str(body[key])
        return None

    def _make_response_handler(self, captured_token: dict[str, Any]) -> Any:
        """创建响应监听器，捕获登录 token"""
        import json as _json

        def handle_response(response: Any) -> None:
            try:
                url = response.url.lower()
                if "/api/" in url:
                    logger.info(f"API 响应: {response.url} (状态: {response.status})")
                if "login" not in url or response.status != 200:
                    return
                content_type = response.headers.get("content-type", "").lower()
                if not ("application/json" in content_type or "text/" in content_type):
                    return
                try:
                    response_body = _json.loads(response.text())
                    if not isinstance(response_body, dict):
                        return
                    token = self._extract_token_from_body(response_body)
                    if token:
                        captured_token["value"] = token
                        logger.info(f"捕获到 Token: {token[:30]}... (长度: {len(token)})")
                    else:
                        logger.warning(f"未能从登录响应中提取 Token，响应结构: {list(response_body.keys())}")
                except Exception as e:
                    logger.error(f"解析登录响应失败: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"响应监听器处理失败: {e}", exc_info=True)

        return handle_response

    def _try_http_login(self, account: str, password: str, max_retries: int) -> dict[str, Any] | None:
        """
        尝试纯 HTTP 逆向登录（无需 Playwright 浏览器）。

        这是一个可插拔的加速方案：
        - 插件位置: apps/automation/services/scraper/sites/court_zxfw_login_private/
        - 插件不入 Git（已在 .gitignore 中忽略），需要手动部署
        - 额外依赖: gmssl（SM2 国密加密）

        可用条件（全部满足才走此路径）:
        1. court_zxfw_login_private/ 目录存在且包含 __init__.py + login_service.py
        2. gmssl 已安装（uv add gmssl）

        不可用时（以下任一情况）自动回退到 Playwright 登录:
        - 插件目录不存在（未部署）
        - gmssl 未安装
        - 纯逆向登录过程中发生异常

        Returns:
            登录结果 dict（成功时），或 None（插件不可用/失败，触发 Playwright 回退）
        """
        try:
            from apps.automation.services.scraper.sites.court_zxfw_login_private import is_available

            if not is_available():
                logger.info("纯逆向登录插件不可用，回退到 Playwright")
                return None

            from apps.automation.services.scraper.sites.court_zxfw_login_private import CourtZxfwHttpLoginService

            svc = CourtZxfwHttpLoginService(captcha_recognizer=self.captcha_recognizer)
            result_raw: object = svc.login(account, password, max_retries=max_retries)
            if not isinstance(result_raw, dict):
                return None
            result: dict[str, Any] = result_raw
            if result.get("success"):
                result["message"] = "纯逆向登录成功"
                result["url"] = self.page.url
            return result
        except Exception as e:
            logger.warning("纯逆向登录异常，回退到 Playwright: %s", e)
            return None

    def _fill_login_form(self, account: str, password: str, save_debug: bool) -> None:
        """填写登录表单（账号、密码、点击密码登录标签）"""
        password_login_xpath = (
            "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
            "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
            "/uni-view[1]/uni-view[2]/uni-view[2]"
        )
        try:
            password_tab = self.page.locator(f"xpath={password_login_xpath}")
            password_tab.wait_for(state="visible", timeout=10000)
            password_tab.click()
            self._random_wait(1, 2)
            if save_debug:
                self._save_screenshot("02_password_tab_clicked")
        except Exception as e:
            logger.warning(f"点击密码登录失败: {e}，可能已经在密码登录页面")

        account_xpath = (
            "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
            "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
            "/uni-view[1]/uni-view[3]/uni-view[1]/uni-view/uni-view/uni-input/div/input"
        )
        account_input = self.page.locator(f"xpath={account_xpath}")
        account_input.wait_for(state="visible", timeout=10000)
        account_input.fill(account)
        self._random_wait(0.5, 1)

        password_xpath = (
            "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
            "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
            "/uni-view[1]/uni-view[3]/uni-view[2]/uni-view/uni-view/uni-input/div/input"
        )
        password_input = self.page.locator(f"xpath={password_xpath}")
        password_input.wait_for(state="visible", timeout=10000)
        password_input.fill(password)
        self._random_wait(0.5, 1)
        if save_debug:
            self._save_screenshot("03_credentials_filled")

    def _is_network_error(self, exc: Exception) -> bool:
        """判断是否为网络相关异常。"""
        if isinstance(exc, (ConnectionError, TimeoutError, socket.gaierror)):
            return True

        if isinstance(exc, OSError) and getattr(exc, "errno", None) in {8, 60, 61, 64, 65}:
            return True

        msg = str(exc).lower()
        network_tokens = (
            "err_internet_disconnected",
            "err_name_not_resolved",
            "err_connection_timed_out",
            "err_connection_closed",
            "err_connection_refused",
            "err_network_changed",
            "name or service not known",
            "nodename nor servname provided",
            "temporary failure in name resolution",
            "timeout",
        )
        return any(token in msg for token in network_tokens)

    def _goto_with_retry(self, url: str, *, max_attempts: int = 2, timeout_ms: int = 30000) -> None:
        """页面导航（轻量重试，提升弱网环境鲁棒性）。"""
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                return
            except Exception as e:
                last_exc = e
                if not self._is_network_error(e):
                    raise
                if attempt < max_attempts:
                    logger.warning("页面导航失败，准备重试(%d/%d): %s", attempt, max_attempts, e)
                    self._random_wait(1, 2)

        if last_exc is not None:
            raise last_exc

    def login(
        self,
        account: str,
        password: str,
        max_captcha_retries: int = 3,
        save_debug: bool = False,
        credential_id: int | None = None,
    ) -> dict[str, Any]:
        """登录全国法院"一张网" """
        logger.info("=" * 60)
        logger.info("开始登录全国法院'一张网'...")
        logger.info("=" * 60)

        # ── 第1优先: Cookie 登录（最快，无需任何请求）──
        if self._cookie_service is not None:
            cookie_path = self._get_cookie_path(account)
            loaded = self._cookie_service.load(self.context, cookie_path)
            if loaded:
                logger.info("已加载 Cookie，尝试跳过登录")
                try:
                    self._goto_with_retry(self.BASE_URL, max_attempts=2)
                except Exception as e:
                    if self._is_network_error(e):
                        logger.warning("Cookie 快速登录网络异常，回退完整登录: %s", e)
                    else:
                        raise
                else:
                    if self._check_login_success():
                        logger.info("Cookie 有效，跳过登录")
                        self.is_logged_in = True
                        return {
                            "success": True,
                            "message": "Cookie 登录成功",
                            "url": self.page.url,
                            "token": None,
                            "used_cookie": True,
                        }
                    logger.info("Cookie 无效，执行完整登录流程")

        # ── 第2优先: 纯 HTTP 逆向登录（可插拔插件，无需浏览器，更快）──
        # 插件位置: apps/automation/services/scraper/sites/court_zxfw_login_private/
        # 没有此目录或 gmssl 未安装时，自动跳过，走下面的 Playwright 登录
        http_result = self._try_http_login(account, password, max_captcha_retries)
        if http_result and http_result.get("success"):
            self.is_logged_in = True
            return http_result

        # ── 第3优先: Playwright 浏览器自动化登录（兜底方案）──
        captured_token: dict[str, Any] = {"value": None}
        try:
            self.page.on("response", self._make_response_handler(captured_token))
            logger.info("✅✅✅ 已设置响应监听器，准备捕获 Token")

            logger.info(f"导航到登录页: {self.LOGIN_URL}")
            self._goto_with_retry(self.LOGIN_URL, max_attempts=2)
            self._random_wait(2, 3)
            if save_debug:
                self._save_screenshot("01_login_page")

            self._fill_login_form(account, password, save_debug)

            if not self._try_captcha_login(
                max_captcha_retries=max_captcha_retries, save_debug=save_debug, captured_token=captured_token
            ):
                raise ValueError("登录失败")

            # 登录成功后保存 Cookie
            if self._cookie_service is not None:
                self._save_cookies(account)

            return {"success": True, "message": "登录成功", "url": self.page.url, "token": captured_token["value"]}

        except Exception as e:
            if self._is_network_error(e):
                logger.warning("登录失败（网络异常）: %s", e)
            else:
                logger.error(f"登录失败: {e}", exc_info=True)
            if save_debug:
                self._save_screenshot("error_login_failed")
            if self._is_network_error(e):
                raise ConnectionError(f"登录失败: 网络连接异常（{e}）") from e
            raise ValueError(f"登录失败: {e}") from e

    def _get_cookie_path(self, account: str) -> str:
        """获取 Cookie 存储路径"""
        safe_account = account.replace("@", "_at_").replace("/", "_")
        return f"cookies/{self.site_name}/{safe_account}.json"

    def _save_cookies(self, account: str) -> None:
        """保存当前浏览器上下文的 Cookie"""
        if self._cookie_service is None:
            return
        cookie_path = self._get_cookie_path(account)
        self._cookie_service.save(self.context, cookie_path)
        logger.info("Cookie 已保存", extra={"account": account, "path": cookie_path})

    def _try_captcha_login(
        self, max_captcha_retries: int, save_debug: bool, captured_token: dict[str, Any] | None = None
    ) -> bool:
        """
        带重试的验证码识别和登录

        Returns:
            登录是否成功
        """
        captcha_input_xpath = (
            "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
            "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
            "/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[1]/uni-view/uni-input/div/input"
        )
        login_button_xpath = (
            "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
            "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
            "/uni-view[1]/uni-view[4]"
        )

        for attempt in range(1, max_captcha_retries + 1):
            logger.info(f"验证码识别尝试 {attempt}/{max_captcha_retries}")
            try:
                captcha_text = self._recognize_captcha(save_debug=save_debug)
                if not captcha_text:
                    logger.warning(f"验证码识别失败（尝试 {attempt}）")
                    if attempt < max_captcha_retries:
                        self._refresh_captcha()
                        continue
                    raise ValueError("验证码识别失败，已达最大重试次数")

                captcha_input = self.page.locator(f"xpath={captcha_input_xpath}")
                captcha_input.wait_for(state="visible", timeout=10000)
                captcha_input.fill(captcha_text)
                self._random_wait(0.5, 1)

                if save_debug:
                    self._save_screenshot(f"04_captcha_filled_attempt_{attempt}")

                login_button = self.page.locator(f"xpath={login_button_xpath}")
                login_button.wait_for(state="visible", timeout=10000)
                login_button.click()

                # 等待 Token 捕获（最多 10 秒）
                # 必须用 page.wait_for_timeout 而非 time.sleep，否则 Playwright 事件回调不会触发
                for _ in range(20):
                    self.page.wait_for_timeout(500)
                    if captured_token and captured_token.get("value"):
                        break

                # 优先检查是否已捕获到 Token（比 URL 检查更可靠）
                if captured_token and captured_token.get("value"):
                    logger.info("已捕获到 Token，登录成功")
                    self.is_logged_in = True
                    return True

                if save_debug:
                    self._save_screenshot(f"05_after_login_attempt_{attempt}")

                if self._check_login_success():
                    logger.info("登录成功")
                    self.is_logged_in = True
                    return True

                logger.warning(f"登录失败（尝试 {attempt}），可能是验证码错误")
                if attempt < max_captcha_retries:
                    captcha_input.fill("")
                    self._refresh_captcha()
                else:
                    raise ValueError("登录失败，已达最大重试次数")

            except Exception as e:
                logger.error(f"登录尝试 {attempt} 出错: {e}")
                if attempt >= max_captcha_retries:
                    raise
                self._random_wait(2, 3)

        return False

    def _recognize_captcha(self, save_debug: bool = False) -> str | None:
        """
        识别验证码 - 使用注入的识别器

        Args:
            save_debug: 是否保存调试信息

        Returns:
            识别的验证码文本，失败返回 None
        """
        try:
            # 验证码图片 XPath
            captcha_img_xpath = (
                "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
                "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
                "/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[2]/uni-image/img"
            )

            # 等待验证码图片加载
            captcha_img = self.page.locator(f"xpath={captcha_img_xpath}")
            captcha_img.wait_for(state="visible", timeout=10000)
            self._random_wait(0.5, 1)

            if save_debug:
                # 保存验证码图片用于调试
                from django.conf import settings

                captcha_screenshot = captcha_img.screenshot()
                debug_dir = Path(settings.MEDIA_ROOT) / "automation" / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                captcha_path = debug_dir / f"captcha_{int(time.time())}.png"
                with open(captcha_path, "wb") as f:
                    f.write(captcha_screenshot)
                logger.info(f"验证码图片已保存: {captcha_path}")

            # 使用注入的识别器识别验证码
            captcha_text_raw = self.captcha_recognizer.recognize_from_element(self.page, f"xpath={captcha_img_xpath}")
            captcha_text = str(captcha_text_raw) if captcha_text_raw else None

            if captcha_text:
                logger.info(f"验证码识别结果: {captcha_text}")
            else:
                logger.warning("验证码识别失败")

            return captcha_text

        except Exception as e:
            logger.error(f"获取验证码图片失败: {e}")
            return None

    def _refresh_captcha(self) -> None:
        """刷新验证码（点击验证码图片）"""
        try:
            captcha_img_xpath = (
                "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
                "/uni-page-wrapper/uni-page-body/uni-view/uni-view[2]/uni-view[2]"
                "/uni-view[1]/uni-view[3]/uni-view[3]/uni-view[2]/uni-image/img"
            )
            captcha_img = self.page.locator(f"xpath={captcha_img_xpath}")
            captcha_img.click()
            logger.info("已刷新验证码")
            self._random_wait(1, 2)
        except Exception as e:
            logger.warning(f"刷新验证码失败: {e}")

    def _check_login_success(self) -> bool:
        """
        检查是否登录成功

        Returns:
            是否登录成功
        """
        try:
            # 方法1: 检查 URL 是否跳转
            current_url = self.page.url
            logger.info(f"当前 URL: {current_url}")

            # 登录成功后通常会跳转到首页或个人中心
            if "login" not in current_url.lower():
                logger.info("URL 已跳转，登录可能成功")
                return True

            # 方法2: 检查是否有错误提示
            try:
                # 查找常见的错误提示元素
                error_selectors = [
                    "text=验证码错误",
                    "text=账号或密码错误",
                    "text=登录失败",
                    ".error-message",
                    ".login-error",
                ]

                for selector in error_selectors:
                    error_elem = self.page.locator(selector)
                    if error_elem.count() > 0 and error_elem.first.is_visible():
                        error_text = error_elem.first.inner_text()
                        logger.warning(f"发现错误提示: {error_text}")
                        return False
            except Exception:
                pass

            # 方法3: 检查是否有用户信息元素（登录后才有）
            try:
                # 等待一些登录后才有的元素
                user_info_selectors = [
                    "text=退出登录",
                    "text=个人中心",
                    ".user-info",
                    ".user-avatar",
                ]

                for selector in user_info_selectors:
                    elem = self.page.locator(selector)
                    if elem.count() > 0:
                        logger.info(f"找到登录后的元素: {selector}")
                        return True
            except Exception:
                pass

            # 默认：如果没有明确的错误，且 URL 变化了，认为成功
            return "login" not in current_url.lower()

        except Exception as e:
            logger.warning(f"检查登录状态失败: {e}")
            return False

    def _random_wait(self, min_sec: float = 0.5, max_sec: float = 2.0) -> None:
        """随机等待"""
        import random

        wait_time = random.uniform(min_sec, max_sec)
        time.sleep(wait_time)

    def _save_screenshot(self, name: str) -> str:
        """保存截图"""
        from datetime import datetime

        from django.conf import settings

        screenshot_dir = Path(settings.MEDIA_ROOT) / "automation" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = screenshot_dir / filename

        self.page.screenshot(path=str(filepath))
        logger.info(f"截图已保存: {filepath}")

        return str(filepath)

    def fetch_baoquan_token(self, save_debug: bool = False) -> dict[str, Any]:
        """登录后跳转到网上保全页面，从 info 接口 URL 中提取 HS512 Token"""
        if not self.is_logged_in:
            raise ValueError("请先登录")

        wsdb_url = "https://zxfw.court.gov.cn/zxfw/#/pagesOther/common/wsdb/index"
        captured: dict[str, Any] = {"value": None}

        def _handle(response: Any) -> None:
            try:
                url = response.url
                if "baoquan.court.gov.cn/wsbq/account/api/info" in url and "token=" in url:
                    token = url.split("token=", 1)[1].split("&", 1)[0]
                    if token:
                        captured["value"] = token
                        logger.info(f"捕获到保全 Token: {token[:30]}... (长度: {len(token)})")
            except Exception as e:
                logger.debug(f"保全响应处理失败: {e}")

        self.page.on("response", _handle)
        try:
            self.page.goto(wsdb_url, timeout=30000, wait_until="networkidle")
            for _ in range(20):
                self.page.wait_for_timeout(500)
                if captured.get("value"):
                    break

            if captured.get("value"):
                return {"success": True, "token": captured["value"]}
            return {"success": False, "message": "未能从保全系统捕获 Token"}
        except Exception as e:
            logger.error(f"获取保全 Token 失败: {e}")
            return {"success": False, "message": str(e)}

    # ==================== 其他功能（待实现） ====================

    def file_case(self, case_data: dict[str, Any]) -> dict[str, Any]:
        """
        立案

        Args:
            case_data: 案件数据

        Returns:
            立案结果
        """
        if not self.is_logged_in:
            raise ValueError("请先登录")

        # TODO: 实现立案逻辑
        raise NotImplementedError("立案功能待实现")

    def query_case(self, case_number: str) -> dict[str, Any]:
        """
        查询案件

        Args:
            case_number: 案号

        Returns:
            案件信息
        """
        if not self.is_logged_in:
            raise ValueError("请先登录")

        # TODO: 实现查询逻辑
        raise NotImplementedError("查询功能待实现")

    def download_document(self, document_url: str) -> dict[str, Any]:
        """
        下载文书

        Args:
            document_url: 文书链接

        Returns:
            下载结果
        """
        if not self.is_logged_in:
            raise ValueError("请先登录")

        # TODO: 实现下载逻辑
        raise NotImplementedError("下载功能待实现")
