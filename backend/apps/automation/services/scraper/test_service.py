"""
测试服务
将测试逻辑从 Admin 层解耦到 Service 层
"""

import logging
import time
import traceback
from typing import TYPE_CHECKING, Any, Optional

from apps.automation.services.scraper.core.screenshot_utils import ScreenshotUtils
from apps.core.config import get_config

if TYPE_CHECKING:
    from apps.automation.services.scraper.core.browser_config import BrowserConfig

logger = logging.getLogger("apps.automation")


class TestService:
    """
    测试服务

    提供各种自动化功能的测试接口
    """

    def __init__(self, organization_service: Any = None, browser_manager: Any = None, config: Any = None) -> None:
        """
        初始化测试服务

        Args:
            organization_service: 组织服务（可选，支持依赖注入）
            browser_manager: 浏览器管理器（可选，支持依赖注入）
            config: 配置对象（可选，支持依赖注入）
        """
        self._organization_service = organization_service
        self._browser_manager = browser_manager
        self._config = config

    @property
    def organization_service(self) -> Any:
        """延迟加载组织服务"""
        if self._organization_service is None:
            from apps.core.interfaces import ServiceLocator

            self._organization_service = ServiceLocator.get_organization_service()
        return self._organization_service

    @property
    def browser_manager(self) -> Any:
        """延迟加载浏览器管理器"""
        if self._browser_manager is None:
            from apps.automation.services.scraper.core.browser_manager import BrowserManager

            self._browser_manager = BrowserManager
        return self._browser_manager

    @property
    def browser_config(self) -> Any:
        """延迟加载浏览器配置"""
        if self._config is None:
            from apps.automation.services.scraper.config.browser_config import BrowserConfig

            self._config = BrowserConfig
        return self._config

    def test_login(self, credential_id: int, config: Optional["BrowserConfig"] = None) -> dict[str, Any]:
        """
        测试账号凭证登录 - 使用 BrowserManager

        Args:
            credential_id: 账号凭证 ID
            config: 浏览器配置，None 则使用默认配置

        Returns:
            测试结果字典
            {
                "success": bool,
                "message": str,
                "screenshots": List[str],
                "logs": List[str],
                "error": Optional[str],
            }
        """
        from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService

        result = {
            "success": False,
            "message": "",
            "screenshots": [],
            "logs": [],
            "error": None,
            "token": None,  # 添加token字段
        }

        try:
            # 1. 获取凭证
            try:
                credential = self.organization_service.get_credential_internal(credential_id)
                result["logs"].append(f"✅ 获取凭证成功: {credential.site_name}")  # type: ignore
                result["logs"].append(f"   账号: {credential.account}")  # type: ignore
            except Exception as e:
                raise ValueError(f"凭证 ID {credential_id} 不存在: {e!s}") from e

            # 2. 加载浏览器配置
            if config is None:
                config = self.browser_config.from_env()
                result["logs"].append("✅ 使用环境变量配置")  # type: ignore
            else:
                result["logs"].append("✅ 使用自定义配置")  # type: ignore

            # 3. 使用 BrowserManager 启动浏览器
            result["logs"].append("🚀 启动浏览器...")  # type: ignore

            with self.browser_manager.create_browser(config) as (page, context):
                result["logs"].append("✅ 浏览器已启动")  # type: ignore

                # 4. 创建服务
                service = CourtZxfwService(page, context)
                result["logs"].append("✅ 服务实例已创建")  # type: ignore

                # 5. 执行登录
                result["logs"].append("🔐 开始登录...")  # type: ignore
                login_result = service.login(
                    account=credential.account,
                    password=credential.password,
                    max_captcha_retries=5,
                    save_debug=True,
                    credential_id=credential_id,
                )

                result["success"] = login_result["success"]
                result["message"] = login_result["message"]
                result["token"] = login_result.get("token")  # 传递token
                result["logs"].append(f"✅ 登录结果: {login_result['message']}")  # type: ignore

                # 记录token信息
                if result["token"]:
                    result["logs"].append(f"🔑 捕获到 Token: {result['token'][:30]}...")  # type: ignore
                    result["logs"].append(f"   Token 长度: {len(result['token'])} 字符")  # type: ignore
                else:
                    result["logs"].append("⚠️ 未捕获到 Token")  # type: ignore

                # 6. 收集截图
                result["logs"].append("📸 收集调试截图...")  # type: ignore
                screenshot_limit = get_config("validation.screenshot_limit", 5)
                result["screenshots"] = ScreenshotUtils.collect_screenshots(limit=screenshot_limit)  # type: ignore
                result["logs"].append(f"✅ 收集到 {len(result['screenshots'])} 张截图")  # type: ignore

                # 7. 等待用户观察
                result["logs"].append("⏳ 等待 30 秒供观察（用于检查浏览器）...")  # type: ignore
                time.sleep(30)

                # 浏览器会自动清理（由 BrowserManager 处理）

            result["logs"].append("✅ 浏览器已关闭")  # type: ignore

        except Exception as e:
            result["success"] = False
            result["message"] = f"登录失败: {e!s}"
            result["error"] = traceback.format_exc()
            result["logs"].append(f"❌ 错误: {e!s}")  # type: ignore
            logger.error(f"测试登录失败: {e}", exc_info=True)

        return result
