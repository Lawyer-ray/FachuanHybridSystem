"""浏览器上下文基础配置。

viewport、locale、timezone 等上下文选项。
指纹伪装（webdriver、canvas、WebRTC 等）由 CloakBrowser C++ 补丁处理。
macOS 平台通过 JS 补充 CloakBrowser 未覆盖的 26→58 差异。
"""

from __future__ import annotations

import logging
import platform
from typing import Any

logger = logging.getLogger("apps.core")

# macOS CloakBrowser 只有 26 个 C++ 补丁（vs Linux 58 个），
# 以下 JS 补丁补充 navigator 属性、屏幕尺寸和 Canvas 指纹。
_MACOS_FINGERPRINT_JS = """
// ── navigator 属性补充 ──
Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'});
Object.defineProperty(navigator, 'appCodeName', {get: () => 'Mozilla'});
Object.defineProperty(navigator, 'appName', {get: () => 'Netscape'});
Object.defineProperty(navigator, 'cookieEnabled', {get: () => true});
Object.defineProperty(navigator, 'doNotTrack', {get: () => null});
Object.defineProperty(navigator, 'vendor', {get: () => 'Google Inc.'});
Object.defineProperty(navigator, 'language', {get: () => 'zh-CN'});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});

// ── 屏幕尺寸 ──
Object.defineProperty(screen, 'width', {get: () => 1920});
Object.defineProperty(screen, 'height', {get: () => 1080});
Object.defineProperty(screen, 'colorDepth', {get: () => 24});
Object.defineProperty(screen, 'pixelDepth', {get: () => 24});

// ── Canvas 指纹随机化 ──
// 每次启动产生微小的像素偏移，使 Canvas 指纹唯一但视觉无差异
(() => {
    const shift = (Math.random() - 0.5) * 0.0001;
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type, quality) {
        try {
            const ctx = this.getContext('2d');
            if (ctx && this.width > 0 && this.height > 0) {
                const imageData = ctx.getImageData(0, 0, Math.min(this.width, 16), Math.min(this.height, 16));
                const d = imageData.data;
                for (let i = 0; i < d.length; i += 4) {
                    d[i] = Math.max(0, Math.min(255, d[i] + (Math.random() > 0.5 ? 1 : 0)));
                }
                ctx.putImageData(imageData, 0, 0);
            }
        } catch(e) {}
        return origToDataURL.apply(this, arguments);
    };

    const origToBlob = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {
        try {
            const ctx = this.getContext('2d');
            if (ctx && this.width > 0 && this.height > 0) {
                const imageData = ctx.getImageData(0, 0, Math.min(this.width, 16), Math.min(this.height, 16));
                const d = imageData.data;
                for (let i = 0; i < d.length; i += 4) {
                    d[i] = Math.max(0, Math.min(255, d[i] + (Math.random() > 0.5 ? 1 : 0)));
                }
                ctx.putImageData(imageData, 0, 0);
            }
        } catch(e) {}
        return origToBlob.apply(this, arguments);
    };
})();
"""

_IS_MACOS = platform.system() == "Darwin"


class AntiDetection:
    """浏览器上下文基础配置。"""

    def get_context_options(self) -> dict[str, Any]:
        """返回浏览器上下文配置（viewport、locale、timezone、headers）。"""
        return {
            "viewport": {"width": 1920, "height": 1080},
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "extra_http_headers": {
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            },
        }

    def apply_macos_patches(self, page: Any) -> None:
        """在 macOS 上补充 CloakBrowser 未覆盖的指纹补丁（同步页面）。"""
        if _IS_MACOS:
            page.add_init_script(_MACOS_FINGERPRINT_JS)
            logger.debug("已应用 macOS 指纹补充补丁")

    async def apply_macos_patches_async(self, page: Any) -> None:
        """在 macOS 上补充 CloakBrowser 未覆盖的指纹补丁（异步页面）。"""
        if _IS_MACOS:
            await page.add_init_script(_MACOS_FINGERPRINT_JS)
            logger.debug("已应用 macOS 指纹补充补丁 (async)")

    # ── 向后兼容方法（已废弃） ──

    def get_random_user_agent(self) -> str:
        return ""

    def apply_stealth(self, context: Any) -> None:
        pass

    async def apply_stealth_async(self, context: Any) -> None:
        pass


anti_detection = AntiDetection()
