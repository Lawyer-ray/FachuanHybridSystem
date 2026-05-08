"""ExpressBrowserQueryService facade — 组合各子模块。"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from apps.express_query.models import ExpressCarrierType

from .browser_launcher import close_browser, disconnect_playwright, ensure_browser
from .ems_query_handler import query_ems
from .sf_query_handler import query_sf

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("apps.express_query")


class ExpressBrowserQueryService:
    @staticmethod
    async def close_browser() -> None:
        await close_browser()

    @staticmethod
    async def disconnect_playwright() -> None:
        await disconnect_playwright()

    async def query_and_save_pdf(self, carrier_type: str, tracking_number: str, output_pdf: Path) -> str:
        output_pdf.parent.mkdir(parents=True, exist_ok=True)

        context = await ensure_browser()
        page = await context.new_page()

        try:
            if carrier_type == ExpressCarrierType.SF:
                await query_sf(page, tracking_number)
            elif carrier_type == ExpressCarrierType.EMS:
                await query_ems(page, tracking_number)
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
