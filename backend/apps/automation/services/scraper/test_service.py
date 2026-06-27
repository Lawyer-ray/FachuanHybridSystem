"""
测试服务
将测试逻辑从 Admin 层解耦到 Service 层
"""
from __future__ import annotations

from typing import Optional
import logging
import time
import traceback
from typing import Any

from apps.automation.services.scraper.core.screenshot_utils import ScreenshotUtils
from apps.core.config import get_config

logger = logging.getLogger("apps.automation")


class TestService:
    """
    测试服务

    提供各种自动化功能的测试接口
    """

    def __init__(self, organization_service: Any = None) -> None:
        """
        初始化测试服务

        Args:
            organization_service: 组织服务（可选，支持依赖注入）
        """
        self._organization_service = organization_service

    @property
    def organization_service(self) -> Any:
        """延迟加载组织服务"""
        if self._organization_service is None:
            from apps.core.interfaces import ServiceLocator

            self._organization_service = ServiceLocator.get_organization_service()
        return self._organization_service

    def test_login(self, credential_id: int, config: Any = None) -> dict[str, Any]:
        """
        测试账号凭证登录

        Args:
            credential_id: 账号凭证 ID
            config: 保留参数（已废弃，不再使用）

        Returns:
            测试结果字典
        """
        from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
        from apps.core.services.browser import create_browser

        result: dict[str, Any] = {
            "success": False,
            "message": "",
            "screenshots": [],
            "logs": [],
            "error": None,
            "token": None,
        }

        try:
            # 1. 获取凭证
            try:
                credential = self.organization_service.get_credential(credential_id)
                result["logs"].append(f"✅ 获取凭证成功: {credential.site_name}")
                result["logs"].append(f"   账号: {credential.account}")
            except Exception as e:
                raise ValueError(f"凭证 ID {credential_id} 不存在: {e!s}") from e

            # 2. 使用正式版 create_browser 启动浏览器
            result["logs"].append("🚀 启动浏览器...")

            with create_browser("court_zxfw") as (page, context):
                result["logs"].append("✅ 浏览器已启动")

                # 3. 创建服务
                service = CourtZxfwService(page, context)
                result["logs"].append("✅ 服务实例已创建")

                # 4. 执行登录
                result["logs"].append("🔐 开始登录...")
                login_result = service.login(
                    account=credential.account,
                    password=credential.password,
                    max_captcha_retries=5,
                    save_debug=True,
                    credential_id=credential_id,
                )

                result["success"] = login_result["success"]
                result["message"] = login_result["message"]
                result["token"] = login_result.get("token")
                result["logs"].append(f"✅ 登录结果: {login_result['message']}")

                if result["token"]:
                    result["logs"].append(f"🔑 捕获到 Token: {result['token'][:30]}...")
                    result["logs"].append(f"   Token 长度: {len(result['token'])} 字符")
                else:
                    result["logs"].append("⚠️ 未捕获到 Token")

                # 5. 收集截图
                result["logs"].append("📸 收集调试截图...")
                screenshot_limit = get_config("validation.screenshot_limit", 5)
                result["screenshots"] = ScreenshotUtils.collect_screenshots(limit=screenshot_limit)  # type: ignore[call-arg]
                result["logs"].append(f"✅ 收集到 {len(result['screenshots'])} 张截图")

                # 6. 等待用户观察
                # NOTE: time.sleep(30) 是有意为之 — 此方法仅从 Admin 测试按钮调用（sync 上下文），
                # 阻塞是为了让管理员有机会观察浏览器状态，不适用于 async 场景。
                result["logs"].append("⏳ 等待 30 秒供观察（用于检查浏览器）...")
                time.sleep(30)

            result["logs"].append("✅ 浏览器已关闭")

        except Exception as e:
            result["success"] = False
            result["message"] = f"登录失败: {e!s}"
            result["error"] = traceback.format_exc()
            result["logs"].append(f"❌ 错误: {e!s}")
            logger.error(f"测试登录失败: {e}", exc_info=True)

        return result
