"""
LPR 利率种子数据加载服务

从 JSON 种子文件加载 LPR 利率数据到数据库.
仅在表为空时加载,不会覆盖已有数据.
"""

import json
import logging
from pathlib import Path
from typing import Any

from django.db import transaction

from apps.finance.models import LPRRate

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def load_lpr_seed_data(*, force: bool = False) -> dict[str, Any]:
    """从 seed_lpr_rates.json 加载 LPR 利率数据.

    Args:
        force: 为 True 时忽略表非空检查,强制重新加载.

    Returns:
        {"loaded": N, "skipped": bool}
    """
    if not force and LPRRate.objects.exists():
        logger.debug("LPR 利率表非空,跳过种子数据加载")
        return {"loaded": 0, "skipped": True}

    seed_file = DATA_DIR / "seed_lpr_rates.json"
    if not seed_file.exists():
        logger.warning("LPR 种子数据文件不存在: %s", seed_file)
        return {"loaded": 0, "skipped": True}

    data = json.loads(seed_file.read_text(encoding="utf-8"))

    with transaction.atomic():
        if force:
            LPRRate.objects.all().delete()
            logger.info("强制模式: 已清空 LPR 利率表")

        loaded = 0
        for item in data:
            LPRRate.objects.update_or_create(
                effective_date=item["effective_date"],
                defaults={
                    "rate_1y": item["rate_1y"],
                    "rate_5y": item["rate_5y"],
                    "source": item.get("source", "种子数据"),
                    "is_auto_synced": False,
                },
            )
            loaded += 1

    logger.info("LPR 种子数据加载完成: %d 条", loaded)
    # 快照缓存失效：见 rate_service.get_rates_snapshot
    from apps.finance.services.lpr.rate_service import LPRRateService

    LPRRateService.invalidate_rates_cache()
    return {"loaded": loaded, "skipped": False}
