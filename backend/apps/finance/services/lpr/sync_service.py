"""LPR数据同步服务.

提供从中国人民银行官网获取LPR利率数据的功能。
使用 Playwright + CDP 连接真实 Chrome 浏览器，绕过反爬。
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import httpx
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import BusinessException
from typing import Any

if TYPE_CHECKING:
    from apps.finance.models.lpr_rate import LPRRate

logger = logging.getLogger(__name__)

# LPR数据源URL（中国银行，结构稳定无反爬）
LPR_DATA_URL = "https://www.boc.cn/fimarkets/lilv/fd32/201310/t20131031_2591219.html"

# CDP 配置
CDP_URL = "http://localhost:9222"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_USER_DATA_DIR = "/tmp/chrome_lpr_profile"


@dataclass
class LPRData:
    """LPR数据结构."""

    effective_date: date
    rate_1y: Decimal
    rate_5y: Decimal


class LPRSyncService:
    """LPR数据同步服务.

    负责从央行官网获取最新LPR数据并同步到数据库。
    """

    def __init__(self) -> None:
        """Initialize service."""
        self.source = "中国人民银行官网"

    def _ensure_chrome_running(self) -> None:
        """确保 Chrome 以调试模式运行，如果未运行则自动启动。"""
        try:
            resp = httpx.get(f"{CDP_URL}/json/version", timeout=2)
            if resp.status_code == 200:
                return
        except Exception:
            pass

        logger.info("[LPRSync] 启动 Chrome 调试模式...")
        subprocess.Popen(
            [CHROME_PATH, "--remote-debugging-port=9222", f"--user-data-dir={CHROME_USER_DATA_DIR}", "--no-first-run"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(10):
            time.sleep(1)
            try:
                resp = httpx.get(f"{CDP_URL}/json/version", timeout=2)
                if resp.status_code == 200:
                    logger.info("[LPRSync] Chrome 启动成功")
                    return
            except Exception:
                pass

        raise BusinessException(message=_("Chrome 启动失败，请手动启动后重试"), code="CHROME_START_FAILED")

    def sync_latest(self) -> dict[str, Any]:
        """同步最新LPR数据.

        Returns:
            同步结果统计
        """
        logger.info("[LPRSync] Starting LPR data synchronization")

        # 启动 Chrome
        self._ensure_chrome_running()

        try:
            # 使用 Playwright + CDP 获取数据
            lpr_data_list = self._fetch_with_playwright()
        except Exception as e:
            logger.error(f"[LPRSync] Fetch failed: {e}")
            raise BusinessException(message=_(f"获取LPR数据失败: {e}"), code="LPR_SYNC_FAILED")

        if not lpr_data_list:
            raise BusinessException(message=_("无法从央行官网获取LPR数据，未找到有效数据"), code="LPR_SYNC_FAILED")

        # 保存到数据库
        return self._save_lpr_data(lpr_data_list)

    def _fetch_with_playwright(self) -> list[LPRData]:
        """使用 Playwright + CDP 连接真实 Chrome 获取LPR数据.

        Returns:
            LPR数据列表
        """
        from playwright.sync_api import sync_playwright

        logger.info(f"[LPRSync] Fetching LPR data via Playwright + CDP from {LPR_DATA_URL}")

        with sync_playwright() as p:
            # 通过 CDP 连接已运行的 Chrome
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()

            try:
                # 访问页面并等待加载完成
                page.goto(LPR_DATA_URL, wait_until="networkidle", timeout=60000)

                # 等待表格加载
                page.wait_for_selector("table", timeout=30000)

                # 额外等待确保动态内容加载
                page.wait_for_timeout(2000)

                # 直接解析页面表格
                result = self._parse_lpr_table_from_page(page)

                if not result:
                    # 尝试截图调试
                    logger.warning("[LPRSync] No data found, taking screenshot for debug")
                    page.screenshot(path="/tmp/lpr_sync_debug.png")

                return result
            finally:
                page.close()

    def _parse_lpr_table_from_page(self, page: object) -> list[LPRData]:
        """直接从Playwright页面解析LPR表格数据.

        Args:
            page: Playwright页面对象

        Returns:
            LPR数据列表
        """
        lpr_data_list: list[LPRData] = []

        # 获取所有表格行
        rows = page.query_selector_all("table tr")
        logger.info(f"[LPRSync] Found {len(rows)} table rows")

        for row in rows:
            try:
                # 获取行内所有单元格
                cells = row.query_selector_all("td, th")
                if len(cells) < 3:
                    continue

                # 提取文本内容
                date_text = cells[0].inner_text().strip()
                rate_1y_text = cells[1].inner_text().strip()
                rate_5y_text = cells[2].inner_text().strip()

                # 跳过表头行
                if date_text in ["LPR报价", "日期", ""] or not date_text:
                    continue

                # 解析日期 (YYYY-MM-DD 格式)
                effective_date = self._parse_date(date_text)
                if not effective_date:
                    continue

                # 解析利率 (带 % 符号)
                rate_1y = self._parse_rate(rate_1y_text)
                rate_5y = self._parse_rate(rate_5y_text)

                if rate_1y is None:
                    continue

                lpr_data_list.append(
                    LPRData(effective_date=effective_date, rate_1y=rate_1y, rate_5y=rate_5y or rate_1y)
                )

            except Exception as e:
                logger.debug(f"[LPRSync] Failed to parse row: {e}")
                continue

        # 去重并排序
        seen_dates = set()
        unique_data = []
        for data in sorted(lpr_data_list, key=lambda x: x.effective_date, reverse=True):
            if data.effective_date not in seen_dates:
                seen_dates.add(data.effective_date)
                unique_data.append(data)

        logger.info(f"[LPRSync] Parsed {len(unique_data)} unique LPR records")
        return unique_data

    def _parse_date(self, date_text: str) -> date | None:
        """解析日期文本.

        Args:
            date_text: 日期文本，如 "2024年3月20日"

        Returns:
            解析后的日期或None
        """
        # 匹配各种日期格式
        patterns = [
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
            r"(\d{4})-(\d{1,2})-(\d{1,2})",
            r"(\d{4})/(\d{1,2})/(\d{1,2})",
        ]

        for pattern in patterns:
            match = re.search(pattern, date_text)
            if match:
                year, month, day = map(int, match.groups())
                try:
                    return date(year, month, day)
                except ValueError:
                    continue

        return None

    def _parse_rate(self, rate_text: str) -> Decimal | None:
        """解析利率文本.

        Args:
            rate_text: 利率文本，如 "3.45%" 或 "3.45"

        Returns:
            解析后的利率或None
        """
        # 提取数字部分
        match = re.search(r"(\d+\.?\d*)", rate_text.replace("%", ""))
        if not match:
            return None

        try:
            rate = Decimal(match.group(1))
            # 如果数字大于10，假设是百分比形式（如345表示3.45%）
            if rate > 10:
                rate = rate / Decimal("100")
            return rate
        except (InvalidOperation, ValueError):
            return None

    def _save_lpr_data(self, lpr_data_list: list[LPRData]) -> dict[str, Any]:
        """保存LPR数据到数据库.

        Args:
            lpr_data_list: LPR数据列表

        Returns:
            同步结果统计
        """
        from apps.finance.models.lpr_rate import LPRRate

        created_count = 0
        updated_count = 0
        skipped_count = 0

        with transaction.atomic():
            for data in lpr_data_list:
                try:
                    obj, created = LPRRate.objects.update_or_create(
                        effective_date=data.effective_date,
                        defaults={
                            "rate_1y": data.rate_1y,
                            "rate_5y": data.rate_5y,
                            "source": self.source,
                            "is_auto_synced": True,
                        },
                    )
                    if created:
                        created_count += 1
                        logger.info(f"[LPRSync] Created LPR record: {data.effective_date}")
                    else:
                        updated_count += 1
                        logger.info(f"[LPRSync] Updated LPR record: {data.effective_date}")
                except Exception as e:
                    skipped_count += 1
                    logger.warning(f"[LPRSync] Failed to save LPR data for {data.effective_date}: {e}")

        result = {
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "total": len(lpr_data_list),
        }

        logger.info(f"[LPRSync] Sync completed: {result}")
        return result

    def get_sync_status(self) -> dict[str, Any]:
        """获取同步状态.

        Returns:
            同步状态信息
        """
        from apps.finance.models.lpr_rate import LPRRate

        latest_rate = LPRRate.objects.first()
        auto_synced_count = LPRRate.objects.filter(is_auto_synced=True).count()
        total_count = LPRRate.objects.count()

        return {
            "latest_rate_date": latest_rate.effective_date if latest_rate else None,
            "total_records": total_count,
            "auto_synced_records": auto_synced_count,
            "manual_records": total_count - auto_synced_count,
        }
