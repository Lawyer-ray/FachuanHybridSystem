from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from apps.express_query.models import ExpressCarrierType

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page

logger = logging.getLogger("apps.express_query")

SF_HOME_URL: Final[str] = "https://www.sf-express.com/"
SF_QUERY_URL: Final[str] = "https://www.sf-express.com/chn/sc/waybill/list"
EMS_HOME_URL: Final[str] = "https://www.11183.com.cn/"
EMS_QUERY_URL: Final[str] = "https://www.11183.com.cn/?to=%2Fquery_express_delivery"

# EMS 协议相关 XPath（与 test_ems_full_flow.py 保持一致）
_EMS_LOGIN_AGREE_CHECKBOX_XPATH: Final[str] = (
    "//*[@id='app']/div[1]/div/header/div[1]/div/div/div[3]" "/div/div[2]/div/div[2]/div[3]/div[1]/label/span/span"
)
_EMS_AGREEMENT_MODAL_XPATH: Final[str] = "//*[@id='app']/div[2]"
_EMS_AGREEMENT_LAST_CLAUSE_XPATH: Final[str] = "//*[@id='app']/div[2]/div/div[2]/div/div[1]/div[1]/ul/li[5]/div/p"
_EMS_AGREEMENT_ACCEPT_BUTTON_XPATH: Final[str] = "//*[@id='app']/div[2]/div/div[2]/div/div[1]/div[2]/div[3]/button[2]"

# Global state
_browser_context: BrowserContext | None = None
_CDP_PORT: Final[int] = 9222
_CDP_URL: Final[str] = f"http://127.0.0.1:{_CDP_PORT}"
_user_data_dir: Path = Path(tempfile.mkdtemp(prefix="express_chrome_"))
_chrome_process: subprocess.Popen[str] | None = None


class ExpressBrowserQueryService:
    @staticmethod
    async def close_browser() -> None:
        global _browser_context, _chrome_process
        if _browser_context is not None:
            try:
                await _browser_context.close()
            except Exception:
                pass
            _browser_context = None
        if _chrome_process is not None:
            try:
                _chrome_process.terminate()
                _chrome_process.wait(timeout=5)
            except Exception:
                try:
                    _chrome_process.kill()
                except Exception:
                    pass
            _chrome_process = None
        logger.info("Browser closed")

    @staticmethod
    async def _ensure_browser() -> BrowserContext:
        """
        Get available browser context (auto-launch Chrome + CDP connect).

        Strategy:
        1. Reuse existing context in current process
        2. Try CDP connect to existing Chrome
        3. Auto-launch Chrome with debug port, then CDP connect

        SF and EMS share the same Chrome window.
        """
        from playwright.async_api import async_playwright

        global _browser_context, _chrome_process

        # Case 1: existing context is alive -> reuse
        if _browser_context is not None and _browser_context.pages:
            try:
                page = await _browser_context.new_page()
                await page.evaluate("1+1")
                await page.close()
                return _browser_context
            except Exception:
                _browser_context = None

        pw = await async_playwright().start()

        # Case 2: try CDP connect to existing Chrome
        browser = await ExpressBrowserQueryService._try_cdp_connect(pw)
        if browser is not None:
            ctx_list = list(browser.contexts)
            _browser_context = (
                ctx_list[0]
                if ctx_list
                else await browser.new_context(
                    viewport={"width": 1440, "height": 900},
                )
            )
            logger.info("Connected to existing Chrome via CDP")
            return _browser_context

        # Case 3: auto-launch Chrome then connect
        ExpressBrowserQueryService._launch_chrome()
        await asyncio.sleep(2)

        browser = await ExpressBrowserQueryService._try_cdp_connect(pw, retries=10, delay=0.5)
        if browser is not None:
            ctx_list2 = list(browser.contexts)
            _browser_context = (
                ctx_list2[0]
                if ctx_list2
                else await browser.new_context(
                    viewport={"width": 1440, "height": 900},
                )
            )
            logger.info("Connected to auto-launched Chrome")
            return _browser_context

        raise RuntimeError(
            f"Cannot connect via CDP ({_CDP_URL}) after launching Chrome." " Check if Chrome is installed correctly."
        )

    @staticmethod
    async def _try_cdp_connect(
        pw: Any,
        retries: int = 1,
        delay: float = 0,
    ) -> Browser | None:
        """Try connecting to Chrome via CDP. Returns Browser or None."""
        for attempt in range(retries):
            try:
                browser: Browser = await pw.chromium.connect_over_cdp(_CDP_URL)
                return browser
            except Exception:
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
        return None

    @staticmethod
    def _launch_chrome() -> None:
        """Auto-launch Chrome with remote debugging port enabled."""
        import platform

        global _chrome_process

        system_name = platform.system().lower()
        if system_name == "darwin":
            chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        elif system_name == "linux":
            chrome_path = "google-chrome"
        else:
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

        _user_data_dir.mkdir(parents=True, exist_ok=True)

        cmd: list[str] = [
            chrome_path,
            f"--remote-debugging-port={_CDP_PORT}",
            f"--user-data-dir={_user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
        ]

        try:
            _chrome_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(
                "Auto-launched Chrome (PID=%d), debug port=%d",
                int(_chrome_process.pid or 0),
                _CDP_PORT,
            )
        except FileNotFoundError:
            raise RuntimeError(f"Chrome not found at: {chrome_path}") from None
        except OSError as exc:
            raise RuntimeError(f"Failed to launch Chrome: {exc}") from exc

    async def query_and_save_pdf(self, carrier_type: str, tracking_number: str, output_pdf: Path) -> str:
        output_pdf.parent.mkdir(parents=True, exist_ok=True)

        context = await self._ensure_browser()
        page = await context.new_page()

        try:
            if carrier_type == ExpressCarrierType.SF:
                await self._query_sf(page, tracking_number)
            elif carrier_type == ExpressCarrierType.EMS:
                await self._query_ems(page, tracking_number)
            else:
                raise ValueError(f"Unsupported carrier: {carrier_type}")

            final_url = str(page.url)

            # EMS 详情页加载较慢，等待完全加载
            if carrier_type == ExpressCarrierType.EMS:
                try:
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    logger.info("EMS page fully loaded")
                except Exception:
                    logger.warning("EMS networkidle timeout, proceeding with PDF anyway")
                await asyncio.sleep(2)

            # 注入日期时间 + URL 页眉
            from datetime import datetime

            now_str: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            watermark_id: str = "__express_watermark__"
            await page.evaluate(
                """([text, url, id]) => {
                    const div = document.createElement('div');
                    div.id = id;
                    div.style.cssText =
                        'position:fixed;top:0;left:0;right:0;z-index:2147483647;' +
                        'background:rgba(0,0,0,0.75);color:#fff;padding:6px 16px;' +
                        'font-size:12px;font-family:-apple-system,sans-serif;' +
                        'display:flex;justify-content:space-between;pointer-events:none;';
                    div.innerHTML = '<span>' + text + '</span><span style="opacity:0.7;max-width:60%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + url + '</span>';
                    document.body.appendChild(div);
                }""",
                [now_str, final_url, watermark_id],
            )
            await asyncio.sleep(0.3)

            await page.pdf(
                path=str(output_pdf),
                format="A4",
                print_background=True,
                margin={"top": "40px", "bottom": "20px", "left": "20px", "right": "20px"},
            )

            # 移除页眉
            await page.evaluate(
                "(id) => { const el = document.getElementById(id); if (el) el.remove(); }",
                watermark_id,
            )

            return final_url
        finally:
            try:
                await page.close()
                logger.info("Closed query result tab")
            except Exception:
                pass

    async def _query_sf(self, page: Page, tracking_number: str) -> None:
        await page.goto(SF_HOME_URL, wait_until="networkidle")
        await asyncio.sleep(2)
        await self._dismiss_sf_overlays(page)

        await self._click_first(
            page,
            [
                "button:has-text('登录')",
                "a:has-text('登录')",
                ".login-btn",
            ],
        )

        logger.info("SF page opened, please login in the browser")
        await self._wait_for_login(
            page,
            login_selectors=["button:has-text('登录')", "a:has-text('登录')"],
            user_selectors=["[class*='user']", "[class*='avatar']", "text=退出登录"],
            timeout_seconds=300,
        )

        await page.goto(SF_QUERY_URL, wait_until="networkidle")
        await asyncio.sleep(3)
        await self._dismiss_sf_overlays(page)

        await self._fill_first(
            page,
            [
                "input[placeholder*='查询']",
                "input[type='text']",
            ],
            tracking_number,
        )
        if not await self._click_first(page, ["button:has-text('查')", "button.search-icon"]):
            await page.keyboard.press("Enter")
        await asyncio.sleep(3)

        await self._open_sf_waybill_detail(page, tracking_number)

    async def _dismiss_sf_overlays(self, page: Page) -> None:
        close_selectors = [
            ".guide-close",
            ".driver-close-btn",
            "[class*='guide'] [class*='close']",
            "[class*='tour'] [class*='close']",
            "[class*='mask'] [class*='close']",
            "button[class*='skip']",
            "button:has-text('下一步')",
            "button:has-text('完成')",
            "button:has-text('跳过')",
            "button:has-text('知道了')",
            "button:has-text('我知道了')",
            "button:has-text('关闭')",
            "button:has-text('暂不')",
            "button:has-text('同意')",
            "span:has-text('下一步')",
            "span:has-text('完成')",
            "span:has-text('同意')",
            ".el-dialog__close",
            ".el-message-box__close",
        ]

        logger.info("  Dismissing SF overlays...")
        for _ in range(10):
            closed_any = False

            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
            except Exception:
                pass

            try:
                next_button = page.get_by_role("button", name="下一步")
                if await next_button.count() > 0 and await next_button.first.is_visible():
                    await next_button.first.click(force=True, timeout=1500)
                    logger.info("  Clicked guide button")
                    await asyncio.sleep(0.8)
                    closed_any = True
                    continue
            except Exception:
                pass

            try:
                agree_button = page.get_by_role("button", name="同意")
                if await agree_button.count() > 0 and await agree_button.first.is_visible():
                    await agree_button.first.click(force=True, timeout=1500)
                    logger.info("  Clicked agree button")
                    await asyncio.sleep(0.8)
                    closed_any = True
            except Exception:
                pass

            for selector in close_selectors:
                if await self._click_first(page, [selector]):
                    logger.info("  Clicked overlay control: %s", selector)
                    await asyncio.sleep(0.5)
                    closed_any = True

            try:
                overlay_boxes = await page.evaluate("""() => Array.from(document.querySelectorAll('body *'))
                    .map((element) => {
                        const htmlElement = element;
                        const style = window.getComputedStyle(htmlElement);
                        const rect = htmlElement.getBoundingClientRect();
                        return {
                            position: style.position,
                            zIndex: Number(style.zIndex || '0'),
                            width: rect.width,
                            height: rect.height,
                            left: rect.left,
                            top: rect.top,
                            right: rect.right,
                        };
                    })
                    .filter((item) =>
                        item.position === 'fixed' &&
                        item.zIndex >= 10 &&
                        item.width >= 180 &&
                        item.height >= 80 &&
                        item.top >= 0
                    )
                    .slice(0, 6)""")
                for box in overlay_boxes:
                    try:
                        await page.mouse.click(box["right"] - 18, box["top"] + 18)
                        logger.info("  Clicked overlay corner")
                        await asyncio.sleep(0.5)
                        closed_any = True
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                await page.evaluate("""() => {
                        document.querySelectorAll('.mask').forEach((element) => {
                            element.classList.remove('mask');
                            element.style.pointerEvents = 'auto';
                        });
                        document.querySelectorAll('[class*="mask"]').forEach((element) => {
                            element.style.pointerEvents = 'none';
                        });
                        document.querySelectorAll('input, button, a').forEach((element) => {
                            element.style.pointerEvents = 'auto';
                        });
                    }""")
            except Exception:
                pass

            if not closed_any:
                break

    async def _open_sf_waybill_detail(self, page: Page, tracking_number: str) -> None:
        logger.info("Opening SF waybill detail: %s", tracking_number)

        detail_button_selectors = [
            "button:has-text('展开详情')",
            "[role='button']:has-text('展开详情')",
            "span:has-text('展开详情')",
            "text=展开详情",
            "button:has-text('查看详情')",
        ]
        verification_selectors = [
            "text=收起详情",
            "text=物流轨迹",
            "text=签收时间",
            "text=签收详情",
            "text=收方",
            "text=寄方",
        ]

        deadline = asyncio.get_running_loop().time() + 30
        while asyncio.get_running_loop().time() < deadline:
            await self._dismiss_sf_overlays(page)

            detail_opened = False
            for selector in detail_button_selectors:
                if await self._click_first(page, [selector]):
                    logger.info("  Clicked expand detail: %s", selector)
                    await asyncio.sleep(2)
                    detail_opened = True
                    break

            if not detail_opened:
                try:
                    clicked = await page.evaluate("""() => {
                        const elements = Array.from(document.querySelectorAll('body *'));
                        for (const element of elements) {
                            const text = (element.innerText || '').trim();
                            if (!text || !text.includes('\u5c55\u5f00\u8be6\u60c5')) {
                                continue;
                            }
                            let current = element;
                            while (current) {
                                if (
                                    current.tagName === 'A' ||
                                    current.tagName === 'BUTTON' ||
                                    current.getAttribute('role') === 'button' ||
                                    current.onclick ||
                                    current.className?.toString().includes('item') ||
                                    current.className?.toString().includes('card')
                                ) {
                                    current.click();
                                    return true;
                                }
                                current = current.parentElement;
                            }
                        }
                        return false;
                    }""")
                    if clicked:
                        logger.info("  Clicked expand detail via DOM search")
                        await asyncio.sleep(2)
                        detail_opened = True
                except Exception:
                    pass

            if detail_opened:
                expand_selectors = [
                    "button:has-text('展开全部轨迹')",
                    "button:has-text('查看全部')",
                    "button:has-text('查看更多')",
                    "button:has-text('展开')",
                ]
                for selector in expand_selectors:
                    await self._click_first(page, [selector])
                await asyncio.sleep(1)

            for selector in verification_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        logger.info("  Detail confirmed: %s", selector)
                        return
                except Exception:
                    pass

            await asyncio.sleep(1)

        raise RuntimeError("SF detail expansion failed: %s" % tracking_number)

    async def _is_ems_dialog_visible(self, page: Page) -> bool:
        """检测 EMS 登录弹窗是否正在显示。"""
        # 方法1: el-dialog.scan 容器可见
        try:
            dialog = page.locator(".el-dialog.scan")
            if await dialog.count() > 0 and await dialog.first.is_visible():
                return True
        except Exception:
            pass
        # 方法2: 可见的"扫码登录"文字
        try:
            qr = page.locator("text=扫码登录")
            if await qr.count() > 0 and await qr.first.is_visible():
                return True
        except Exception:
            pass
        # 方法3: 协议文字
        try:
            agree = page.locator("text=请阅读并同意服务协议")
            if await agree.count() > 0 and await agree.first.is_visible():
                return True
        except Exception:
            pass
        return False

    async def _ems_click_login_button(self, page: Page) -> bool:
        """点击 EMS 页面的「登录/注册」按钮。返回是否点击成功。"""
        selectors: list[str] = [
            "text=登录/注册",
            "a:text('登录/注册')",
            "div:text('登录/注册')",
            "span:text('登录/注册')",
        ]
        for selector in selectors:
            loc = page.locator(selector)
            try:
                count = await loc.count()
            except Exception:
                continue
            for i in range(min(count, 5)):
                target = loc.nth(i)
                try:
                    if await target.is_visible():
                        await target.click(force=True, timeout=3000)
                        return True
                except Exception:
                    continue
        # JS 兜底
        try:
            clicked = await page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('a, div, span, button'));
                for (const el of els) {
                    const t = (el.innerText || '').trim();
                    if ((t === '登录/注册' || t === '登录') && el.getBoundingClientRect().width > 0) {
                        el.click(); return true;
                    }
                }
                return false;
            }""")
            return bool(clicked)
        except Exception:
            return False

    async def _query_ems(self, page: Page, tracking_number: str) -> None:
        """
        EMS 查询主流程：
        1. 用 ?to= 进入（未登录时自动弹登录框）
        2. 检测登录状态：未登录→处理协议+等待扫码；已登录→跳过
        3. 导航到干净的 query_express_delivery 页面（不含 ?to=）
        4. 输入单号搜索 + 打开详情
        """
        from urllib.parse import parse_qs, urlparse

        context = page.context
        _clean_query_url: str = "https://www.11183.com.cn/query_express_delivery"

        # ===== 阶段1: 进入页面（?to= 触发登录弹窗）=====
        await page.goto(EMS_QUERY_URL, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            logger.info("EMS networkidle timeout, continuing")
        await asyncio.sleep(2)

        # ===== 阶段2: 检测并处理登录状态 =====
        dialog_showing = await self._is_ems_dialog_visible(page)
        if dialog_showing:
            logger.info("EMS login dialog auto-showed (via ?to=), no button click needed")
        else:
            logger.info("Login dialog not visible, clicking 登录/注册...")
            clicked = await self._ems_click_login_button(page)
            if clicked:
                await asyncio.sleep(1.5)
                if not await self._is_ems_dialog_visible(page):
                    logger.info("Dialog still not showing, re-clicking...")
                    await self._ems_click_login_button(page)
                    await asyncio.sleep(1)
            else:
                logger.warning("Failed to click login button")

        # ===== 阶段3: 判断是否已登录，否则处理协议 + 等待扫码 =====
        if not await self._is_ems_dialog_visible(page):
            body_text = ""
            try:
                body_text = (await page.locator("body").text_content()) or ""
            except Exception:
                pass
            _logged_in_keywords = ("退出", "我的EMS", "个人中心", "我的快递")
            if any(kw in body_text for kw in _logged_in_keywords):
                logger.info("EMS user already logged in, skipping login flow")
            else:
                logger.info("Starting EMS agreement handling + login wait...")
                await self._ems_handle_agreement_and_wait(context, page, timeout_seconds=300)
        else:
            logger.info("Starting EMS agreement handling + login wait...")
            await self._ems_handle_agreement_and_wait(context, page, timeout_seconds=300)

        # ===== 阶段4: 导航到干净查询页（不含 ?to=）再操作 =====
        current_url_lower = page.url.lower()
        if (
            "personal_center" in current_url_lower
            or "query_express_delivery" not in current_url_lower
            or "?to=" in page.url
        ):
            logger.info("Navigating to clean query page: %s", _clean_query_url)
            await page.goto(_clean_query_url, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            await asyncio.sleep(2)

        await self._dismiss_ems_overlays(page)

        await self._fill_first(
            page,
            [
                "input[placeholder*='邮件号']",
                "input[placeholder*='搜索']",
                "input[type='search']",
                "input[type='text']",
            ],
            tracking_number,
        )

        if not await self._click_first(
            page,
            [
                "button:has-text('搜索')",
                "button:has-text('查询')",
                "button:has-text('查件')",
            ],
        ):
            await page.keyboard.press("Enter")
        await asyncio.sleep(3)

        await self._open_ems_waybill_detail(page, tracking_number)

    async def _dismiss_ems_overlays(self, page: Page) -> None:
        close_selectors = [
            "button:has-text('知道了')",
            "button:has-text('我知道了')",
            "button:has-text('同意')",
            "button:has-text('关闭')",
            "button:has-text('跳过')",
            "button:has-text('稍后')",
            "button:has-text('确定')",
            "span:has-text('关闭')",
            "span:has-text('知道了')",
            ".close-btn",
            ".icon-close",
            "[class*='dialog'] [role='button']",
            "[class*='popup'] [role='button']",
            "[class*='mask'] [class*='close']",
        ]

        logger.info("  Dismissing EMS popups...")
        for _ in range(8):
            closed_any = False

            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.2)
            except Exception:
                pass

            for selector in close_selectors:
                if await self._click_first(page, [selector]):
                    logger.info("  Clicked popup control: %s", selector)
                    closed_any = True

            try:
                clicked = await page.evaluate("""() => {
                        const elements = Array.from(document.querySelectorAll('body *'));
                        for (const element of elements) {
                            const htmlElement = element;
                            const style = window.getComputedStyle(htmlElement);
                            const rect = htmlElement.getBoundingClientRect();
                            // 提高阈值：只关闭真正的大弹窗，避免误点卡片/内容区
                            if (
                                style.position === 'fixed' &&
                                Number(style.zIndex || '0') >= 100 &&
                                rect.width >= 300 &&
                                rect.height >= 200
                            ) {
                                const x = rect.right - 18;
                                const y = rect.top + 18;
                                const target = document.elementFromPoint(x, y);
                                if (target instanceof HTMLElement) {
                                    target.click();
                                    return true;
                                }
                            }
                        }
                        return false;
                    }""")
                if clicked:
                    logger.info("  Clicked popup corner")
                    await asyncio.sleep(0.5)
                    closed_any = True
            except Exception:
                pass

            try:
                await page.evaluate("""() => {
                        document.querySelectorAll('[class*="mask"], [class*="overlay"], [class*="modal-bg"]').forEach((element) => {
                            element.style.pointerEvents = 'none';
                        });
                        document.querySelectorAll('button, a, input, textarea, [role="button"]').forEach((element) => {
                            element.style.pointerEvents = 'auto';
                        });
                    }""")
            except Exception:
                pass

            if not closed_any:
                break

    async def _open_ems_waybill_detail(self, page: Page, tracking_number: str) -> None:
        logger.info("Opening EMS mail detail: %s", tracking_number)

        detail_button_selectors = [
            "button:has-text('查看详情')",
            "button:has-text('详情')",
            "button:has-text('物流详情')",
            "button:has-text('邮件详情')",
            "button:has-text('收寄详情')",
            "a:has-text('查看详情')",
            "a:has-text('详情')",
        ]
        detail_state_selectors = [
            "text=物流轨迹",
            "text=收寄详情",
            "text=收件人",
            "text=寄件人",
            "text=签收",
            "text=妥投",
        ]

        deadline = asyncio.get_running_loop().time() + 45
        detail_action_done = False
        dismiss_count: int = 0

        while asyncio.get_running_loop().time() < deadline:
            # 只在前 3 次循环尝试关闭弹窗，防止死循环误关内容
            if dismiss_count < 3:
                await self._dismiss_ems_overlays(page)
                dismiss_count += 1

            try:
                await self._click_first(page, [f"text={tracking_number}"])
            except Exception:
                pass

            try:
                clicked_detail_from_dom = await page.evaluate(
                    """(trackingNumber) => {
                        const normalizedTarget = String(trackingNumber).replace(/\\s+/g, '');
                        const elements = Array.from(document.querySelectorAll('body *'));
                        for (const element of elements) {
                            const text = String(element.innerText || element.textContent || '').replace(/\\s+/g, '');
                            if (!text || !text.includes(normalizedTarget)) {
                                continue;
                            }

                            let container = element;
                            for (let depth = 0; depth < 6 && container; depth += 1) {
                                const detailNode = Array.from(container.querySelectorAll('button,a,span,div')).find((node) => {
                                    const nodeText = String(node.innerText || node.textContent || '').trim();
                                    return /\u67e5\u770b\u8be6\u60c5|\u8be6\u60c5|\u7269\u6d41\u8be6\u60c5|\u90ae\u4ef6\u8be6\u60c5|\u6536\u5bc4\u8be6\u60c5/.test(nodeText);
                                });
                                if (detailNode instanceof HTMLElement) {
                                    detailNode.click();
                                    return true;
                                }
                                container = container.parentElement;
                            }
                        }
                        return false;
                    }""",
                    tracking_number,
                )
                if clicked_detail_from_dom:
                    detail_action_done = True
                    logger.info("  Triggered detail click via DOM")
                    await asyncio.sleep(2)
            except Exception:
                pass

            if not detail_action_done:
                for selector in detail_button_selectors:
                    if await self._click_first(page, [selector]):
                        detail_action_done = True
                        logger.info("  Clicked detail button: %s", selector)
                        await asyncio.sleep(2)
                        break

            if detail_action_done:
                expand_selectors = [
                    "button:has-text('展开详情')",
                    "button:has-text('查看详情')",
                    "button:has-text('物流详情')",
                    "button:has-text('邮件详情')",
                    "button:has-text('收寄详情')",
                    "button:has-text('查看更多')",
                    "button:has-text('查看全部')",
                    "button:has-text('全部轨迹')",
                    "button:has-text('展开')",
                ]
                for selector in expand_selectors:
                    await self._click_first(page, [selector])
                await asyncio.sleep(2)

                for selector in detail_state_selectors:
                    try:
                        if await page.locator(selector).count() > 0:
                            logger.info("  EMS detail confirmed: %s", selector)
                            return
                    except Exception:
                        pass

            await asyncio.sleep(1)

        if not detail_action_done:
            raise RuntimeError("EMS detail failed: no click triggered for %s" % tracking_number)
        raise RuntimeError("EMS detail failed: clicked but no detail block appeared for %s" % tracking_number)

    async def _wait_for_login(
        self,
        page: Page,
        *,
        login_selectors: list[str],
        user_selectors: list[str],
        timeout_seconds: int,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout_seconds

        while asyncio.get_running_loop().time() < deadline:
            login_visible = await self._has_any_visible(page, login_selectors)
            user_visible = await self._has_any_visible(page, user_selectors)
            if user_visible or not login_visible:
                return
            await asyncio.sleep(2)

    # ==================== EMS 协议处理（来自 test_ems_full_flow.py） ====================

    @staticmethod
    def _is_ems_login_window(page: Page, body_text: str) -> bool:
        """判断页面是否为 EMS 登录/扫码窗口。"""
        url_lower = page.url.lower()
        url_keywords = ("login", "passport", "auth", "oauth", "qrcode", "wx")
        if any(kw in url_lower for kw in url_keywords):
            return True
        body_keywords = (
            "扫码登录",
            "请使用微信扫码",
            "微信扫码",
            "登录",
            "手机号登录",
            "验证码登录",
        )
        return any(kw in body_text for kw in body_keywords)

    async def _ems_ensure_agreement_checked(self, page: Page) -> bool:
        """勾选"登录即代表您已同意"协议（仅精确 XPath，避免误点）。"""
        exact_checkbox = page.locator(f"xpath={_EMS_LOGIN_AGREE_CHECKBOX_XPATH}")
        if await self._click_locator_if_visible(exact_checkbox, "agreement checkbox (exact XPath)"):
            return True

        # 只用精确文本匹配，不用模糊 class 选择器
        fallback_selectors = [
            "label:has-text('登录即代表您已同意')",
            "span:has-text('登录即代表您已同意')",
        ]
        for selector in fallback_selectors:
            if await self._click_first(page, [selector]):
                logger.info("  Agreement checked via text: %s", selector)
                return True

        # DOM 搜索也限定更精确的关键词
        try:
            clicked = await page.evaluate("""() => {
                    const exactPattern = /\\u767b\\u5f55\\u5373\\u4ee3\\u8868\\u60a8\\u5df2\\u540c\\u610f/;
                    const elements = Array.from(document.querySelectorAll('label, span'));
                    for (const element of elements) {
                        const text = String(element.innerText || element.textContent || '').trim();
                        if (!text || !exactPattern.test(text)) continue;
                        const relatedInput =
                            element.querySelector('input[type="checkbox"]')
                            || element.closest('label')?.querySelector('input[type="checkbox"]')
                            || element.parentElement?.querySelector('input[type="checkbox"]');
                        if (relatedInput instanceof HTMLInputElement) {
                            if (!relatedInput.checked) relatedInput.click();
                            return true;
                        }
                        element.click();
                        return true;
                    }
                    return false;
                }""")
            if clicked:
                logger.info("  Agreement checked via DOM")
                await asyncio.sleep(0.6)
                return True
        except Exception:
            pass
        return False

    async def _ems_scroll_agreement_and_accept(self, agreement_page: Page) -> bool:
        """尝试点击协议确认按钮，若不可点击则提示用户手动操作。"""
        accept_btn = agreement_page.locator(f"xpath={_EMS_AGREEMENT_ACCEPT_BUTTON_XPATH}")
        if await self._click_locator_if_visible(accept_btn, "agreement accept button"):
            return True
        logger.info("  Please scroll to bottom and click '我已阅读并同意' manually")
        return True

    async def _ems_open_last_agreement_and_accept(self, context: BrowserContext, page: Page) -> bool:
        """点击最后一个协议链接 → 滚动到底部 → 点击确认按钮。"""
        pages_before = len(context.pages)

        # 只用精确 XPath 触发，不用模糊选择器避免误点
        trigger_clicked = await self._click_locator_if_visible(
            page.locator(f"xpath={_EMS_LOGIN_AGREE_CHECKBOX_XPATH}"),
            "agreement trigger (exact XPath)",
        )

        if not trigger_clicked:
            logger.info("  Agreement checkbox not found yet (login may still be loading)")
            return False

        # 判断是否打开了新页面（弹窗页）
        agreement_page: Page = page
        if len(context.pages) > pages_before:
            agreement_page = context.pages[-1]

        try:
            await agreement_page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass

        # 等待协议弹层出现
        modal_loc = agreement_page.locator(f"xpath={_EMS_AGREEMENT_MODAL_XPATH}")
        try:
            if await modal_loc.count() > 0:
                await modal_loc.first.wait_for(timeout=4000)
                logger.info("  Agreement modal appeared")
        except Exception:
            pass

        # 点击最后一个条款滚动到底部
        last_clause = agreement_page.locator(f"xpath={_EMS_AGREEMENT_LAST_CLAUSE_XPATH}")
        if await self._click_locator_if_visible(last_clause, "last clause"):
            await asyncio.sleep(0.6)

        accepted = await self._ems_scroll_agreement_and_accept(agreement_page)

        # 如果是新开的页面，关闭它
        if agreement_page is not page:
            try:
                await agreement_page.close()
                logger.info("  Closed agreement page")
            except Exception:
                pass

        return accepted

    async def _ems_handle_agreement_and_wait(self, context: BrowserContext, page: Page, timeout_seconds: int = 300) -> None:
        """
        EMS 完整登录流程：
        - 检测弹窗可见性
        - 自动处理协议（勾选 checkbox → 同意 → 确认）
        - 等待用户扫码
        - 检测登录成功

        基于 ems_explore.py 验证通过的逻辑。
        """
        logger.info("EMS agreement + login wait (timeout=%ds)", timeout_seconds)
        deadline = asyncio.get_running_loop().time() + timeout_seconds

        for attempt in range(20):
            # ---- 检测弹窗状态 ----
            dialog_visible = await self._is_ems_dialog_visible(page)

            # 检测二维码区域（说明可以扫码了）
            has_qr: bool = False
            try:
                qr_loc = page.locator("text=扫码登录")
                if await qr_loc.count() > 0 and await qr_loc.first.is_visible():
                    has_qr = True
            except Exception:
                pass

            # 检测待处理的 checkbox
            has_checkbox: bool = False
            try:
                cb_loc = page.get_by_text("请阅读并同意", exact=False)
                if await cb_loc.count() > 0 and await cb_loc.first.is_visible():
                    has_checkbox = True
            except Exception:
                pass

            logger.info(
                "EMS login round %d: dialog=%s, qr=%s, checkbox=%s",
                attempt + 1,
                dialog_visible,
                has_qr,
                has_checkbox,
            )

            # 二维码出现且无待处理 checkbox → 可以等扫码了
            if has_qr and not has_checkbox:
                logger.info("QR code visible, waiting for user scan...")
                break  # 跳出协议循环，进入等待扫码阶段

            # 弹窗不可见 → 尝试重新打开
            if not dialog_visible:
                reclicked = await self._ems_click_login_button(page)
                if reclicked:
                    await asyncio.sleep(1.5)
                await asyncio.sleep(1)
                continue

            # ---- 尝试点击协议 checkbox ----
            cb_clicked = await self._ems_try_agreement_checkbox(page)

            # 等待可能的协议页面弹出
            await asyncio.sleep(1.5)

            # 检测新标签页（排除当前 page）
            new_tab = None
            for p in context.pages:
                if p is not page and not p.is_closed():
                    new_tab = p
                    break

            if new_tab is not None:
                logger.info("New agreement tab detected: %s", new_tab.url)
                try:
                    await self._ems_accept_agreement_on_page(new_tab)
                    if not new_tab.is_closed():
                        await new_tab.close()
                        logger.info("Agreement tab closed")
                        await asyncio.sleep(1)
                except Exception as e:
                    logger.info("Agreement tab handling failed: %s", e)

            if cb_clicked or has_qr or not dialog_visible:
                await asyncio.sleep(2)
            else:
                logger.info("No change detected, waiting...")
                await asyncio.sleep(2)

        # ===== 等待用户扫码登录 =====
        remaining_secs = max(int(deadline - asyncio.get_running_loop().time()), 0)
        logger.info("Waiting for QR code scan (max %ds)...", remaining_secs)

        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(3)

            still_dialog = await self._is_ems_dialog_visible(page)
            on_query = "query_express_delivery" in page.url.lower()
            body = ""
            try:
                body = (await page.locator("body").text_content()) or ""
            except Exception:
                pass

            has_logged_in_indicators = any(kw in body for kw in ("退出", "我的EMS", "个人中心", "我的快递"))

            # 弹窗关闭 + 在查询页 + 有内容 → 登录成功
            if not still_dialog and on_query and ("邮件号" in body or "物流" in body or "收件" in body):
                logger.info("Login success (dialog closed, on query page)")
                return

            # 跳到 personal_center → 也算成功
            if "personal_center" in page.url.lower():
                logger.info("Login success (redirected to personal_center)")
                return

            # 有已登录标志且弹窗不在了
            if not still_dialog and has_logged_in_indicators:
                logger.info("Login success (logged-in indicators found)")
                return

            remaining_secs = max(int(deadline - asyncio.get_running_loop().time()), 0)
            logger.info("Waiting for scan... (%ds remaining)", remaining_secs)

        raise TimeoutError("EMS login timed out after %ds" % timeout_seconds)

    async def _ems_try_agreement_checkbox(self, page: Page) -> bool:
        """尝试多种策略点击 EMS 协议 checkbox。返回是否点击成功。"""
        # 策略A: XPath 点击 span
        xpaths: list[str] = [
            "//label[contains(., '同意')]/span/span",
            "//label[contains(., '服务协议')]//span[@class]",
        ]
        for xp in xpaths:
            try:
                loc = page.locator(f"xpath={xp}")
                if await loc.count() > 0:
                    await loc.first.click(force=True, timeout=2000)
                    logger.info("Agreement clicked via XPath: %s", xp)
                    await asyncio.sleep(2)
                    return True
            except Exception as e:
                logger.info("XPath failed: %s", e)

        # 策略B: 文本定位整行
        try:
            text_loc = page.get_by_text("请阅读并同意", exact=False)
            if await text_loc.count() > 0:
                await text_loc.first.click(force=True, timeout=2000)
                logger.info("Agreement clicked via text")
                await asyncio.sleep(2)
                return True
        except Exception as e:
            logger.info("Text click failed: %s", e)

        # 策略C: JS 在弹窗内搜索
        try:
            js_res = await page.evaluate("""() => {
                const dialogs = document.querySelectorAll('.el-dialog');
                for (const d of dialogs) {
                    if (d.getBoundingClientRect().width === 0) continue;
                    const candidates = Array.from(d.querySelectorAll(
                        'label, span, div, [class*="check"], [class*="agree"]'
                    )).filter(el => {
                        const t = el.innerText || '';
                        return (t.includes('同意') || t.includes('协议'))
                               && el.getBoundingClientRect().width > 0;
                    });
                    if (candidates.length > 0) { candidates[0].click(); return { ok: true }; }
                }
                const all = Array.from(document.querySelectorAll('*')).filter(el => {
                    const t = el.innerText || '';
                    return (t.includes('请阅读并同意') || t.includes('登录即代表'))
                           && el.getBoundingClientRect().width > 0 && el.children.length < 5;
                });
                all.sort((a, b) => a.innerText.length - b.innerText.length);
                if (all.length > 0) { all[0].click(); return { ok: true }; }
                return { ok: false };
            }""")
            if js_res.get("ok"):
                logger.info("Agreement clicked via JS")
                await asyncio.sleep(2)
                return True
        except Exception as e:
            logger.info("JS click failed: %s", e)

        return False

    async def _ems_accept_agreement_on_page(self, agreement_page: Page) -> None:
        """在协议页面上点最后一个条款 + 点确认按钮。"""
        last_clause_selectors: list[str] = [
            "xpath=//*[@id='app']/div[2]/div/div[2]/div/div[1]/div[1]/ul/li[last()]/div/p",
            "xpath=//*[@id='app']/div[2]/div/div[2]" "/div/div[1]/div[1]/ul/li[5]/div/p",
        ]
        for sel in last_clause_selectors:
            try:
                clause = agreement_page.locator(sel)
                if await clause.count() > 0:
                    await clause.first.click()
                    await asyncio.sleep(0.5)
                    break
            except Exception:
                continue

        accept_selectors: list[str] = [
            "xpath=//*[@id='app']/div[2]/div/div[2]" "/div/div[1]/div[2]/div[3]/button[last()]",
            "xpath=//*[@id='app']/div[2]/div/div[2]" "/div/div[1]/div[2]/div[3]/button[2]",
        ]
        for sel in accept_selectors:
            try:
                btn = agreement_page.locator(sel)
                if await btn.count() > 0:
                    await btn.first.click(timeout=3000)
                    logger.info("Agreement accept button clicked")
                    await asyncio.sleep(1)
                    return
            except Exception:
                continue
        logger.warning("Accept button not found on agreement page")

    @staticmethod
    async def _click_locator_if_visible(locator: Any, description: str) -> bool:
        """点击 Locator 中第一个可见元素。"""
        try:
            count = await locator.count()
        except Exception:
            return False
        for index in range(min(count, 5)):
            target = locator.nth(index)
            try:
                if not await target.is_visible():
                    continue
                await target.scroll_into_view_if_needed()
                await target.click(force=True, timeout=2000)
                logger.info("  Clicked %s", description)
                await asyncio.sleep(1)
                return True
            except Exception:
                continue
        return False

    async def _fill_first(self, page: Page, selectors: list[str], value: str) -> None:
        for selector in selectors:
            locator = page.locator(selector)
            try:
                if await locator.count() == 0:
                    continue
                first = locator.first
                await first.click(force=True)
                await first.fill("")
                await first.fill(value)
                return
            except Exception:
                continue
        raise RuntimeError("No input field found")

    async def _click_first(self, page: Page, selectors: list[str]) -> bool:
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = await locator.count()
            except Exception:
                continue

            for index in range(min(count, 5)):
                candidate = locator.nth(index)
                try:
                    if not await candidate.is_visible():
                        continue
                    await candidate.scroll_into_view_if_needed()
                    await candidate.click(force=True, timeout=2000)
                    return True
                except Exception:
                    continue
        return False

    async def _has_any_visible(self, page: Page, selectors: list[str]) -> bool:
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = await locator.count()
            except Exception:
                continue
            for index in range(min(count, 3)):
                try:
                    if await locator.nth(index).is_visible():
                        return True
                except Exception:
                    continue
        return False
