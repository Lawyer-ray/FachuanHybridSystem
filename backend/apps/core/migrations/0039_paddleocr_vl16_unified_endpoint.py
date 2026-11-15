"""PaddleOCR 配置收口到 v2 Job API，并启用 PaddleOCR-VL-1.6

## 背景

迁移 0012 曾把「每模型一个 URL」的旧同步端点改为 v2 异步 Job API 统一端点，
但线上库里的三个旧键仍残留（PADDLEOCR_OCR_API_URL / PADDLEOCR_VL_API_URL /
PADDLEOCR_VL15_API_URL），且代码仍按旧映射去读它们。

这些 aistudio 体验域名**已全部失效**（实测返回 HTTP 500），导致配了 paddleocr_api
也必然失败。同时旧模型的取值（pp_ocrv5 / paddleocr_vl_1_5）与 PaddleOCR 服务端
要求的官方模型名不一致，提交时报 `10007 模型传参错误`。

## 本次改动

1. 删除三个失效的旧 URL 键（0012 已删过一次，此处再删以清理残留/回滚恢复）
2. 确保 PADDLEOCR_JOB_API_URL 存在
3. PADDLEOCR_API_MODEL 升级为 paddleocr_vl_1_6（生僻字/印章增强，适合法律文书）
4. OCR_PROVIDER 切到 paddleocr_api（本地 RapidOCR 在生僻字上实测出错）
"""

import logging
from typing import Any

from django.db import migrations

logger = logging.getLogger(__name__)

_JOB_API_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"

_DEAD_URL_KEYS = (
    "PADDLEOCR_OCR_API_URL",
    "PADDLEOCR_VL_API_URL",
    "PADDLEOCR_VL15_API_URL",
)

#: 视为「旧默认值 / 未配置」的模型取值。
#:
#: 库里实际混存过两种写法：小写配置键（paddleocr_vl_1_5）和官方名（PP-OCRv6 /
#: PaddleOCR-VL-1.5）—— 两种都要认，否则线上会把 PP-OCRv6 当成「用户显式选过的值」
#: 而跳过升级。
_LEGACY_MODEL_KEYS = {
    "",
    "pp_ocrv5",
    "PP-OCRv5",
    "pp_ocrv6",
    "PP-OCRv6",
    "pp_structure_v3",
    "PP-StructureV3",
    "paddleocr_vl",
    "PaddleOCR-VL",
    "paddleocr_vl_1_5",
    "PaddleOCR-VL-1.5",
}


def apply_paddleocr_configs(apps: Any, schema_editor: Any) -> None:  # pragma: no cover
    SystemConfig = apps.get_model("core", "SystemConfig")

    # ── 1. 删除失效的旧端点配置 ──────────────────────────
    deleted, _ = SystemConfig.objects.filter(key__in=_DEAD_URL_KEYS).delete()

    # ── 2. 统一 Job API 端点 ─────────────────────────────
    SystemConfig.objects.update_or_create(
        key="PADDLEOCR_JOB_API_URL",
        defaults={
            "category": "ocr",
            "description": "PaddleOCR v2 异步 Job API 地址（所有模型共用，靠 model 参数区分产品线）",
            "value": _JOB_API_URL,
            "is_secret": False,
        },
    )

    # ── 3. 模型升级到 VL-1.6 ─────────────────────────────
    model_cfg = SystemConfig.objects.filter(key="PADDLEOCR_API_MODEL").first()
    current_model = str(model_cfg.value or "").strip() if model_cfg else ""
    # 已经指向 VL-1.6 的不动；其余只要属于「未配置 / 旧默认值」就升级。
    # 用户显式选过的其他值（将来如新增）不在 _LEGACY_MODEL_KEYS 里，不会被误改。
    if current_model not in {"paddleocr_vl_1_6", "PaddleOCR-VL-1.6"} and (
        model_cfg is None or current_model in _LEGACY_MODEL_KEYS
    ):
        SystemConfig.objects.update_or_create(
            key="PADDLEOCR_API_MODEL",
            defaults={
                "category": "ocr",
                "description": (
                    "PaddleOCR API 模型选择（"
                    "paddleocr_vl_1_6=最新版-生僻字/印章增强，推荐法律文书, "
                    "paddleocr_vl_1_5=高精度版面分析, "
                    "paddleocr_vl=版面分析+OCR, "
                    "pp_structure_v3=文档结构化-表格/版面, "
                    "pp_ocrv6=纯文字OCR-快但生僻字易错）"
                ),
                "value": "paddleocr_vl_1_6",
                "is_secret": False,
            },
        )

    # ── 4. OCR 引擎切到云端 ──────────────────────────────
    provider_cfg = SystemConfig.objects.filter(key="OCR_PROVIDER").first()
    if provider_cfg is None or str(provider_cfg.value or "").strip().lower() in {"", "local"}:
        # 默认从 local 抬到云端：本地 RapidOCR(PP-OCRv5) 实测在生僻字和常见机构名
        # 上都会出错（把三个字的人名认成形近的另一个字、把银行名认成同音乱码），
        # 不适合直接作为正文产出。
        SystemConfig.objects.update_or_create(
            key="OCR_PROVIDER",
            defaults={
                "category": "ocr",
                "description": "OCR 引擎选择（local=本地 RapidOCR / paddleocr_api=百度 PaddleOCR API）",
                "value": "paddleocr_api",
                "is_secret": False,
            },
        )

    logger.info(
        "PaddleOCR 配置收口完成: 删除旧端点=%d 端点=%s 模型=paddleocr_vl_1_6 引擎=paddleocr_api",
        deleted,
        _JOB_API_URL,
    )


def reverse_paddleocr_configs(apps: Any, schema_editor: Any) -> None:  # pragma: no cover
    """回滚：恢复 OCR_PROVIDER=local（旧端点地址已失效，不恢复）"""
    SystemConfig = apps.get_model("core", "SystemConfig")
    SystemConfig.objects.filter(key="OCR_PROVIDER").update(value="local")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0038_remove_docspace_cloud_docs"),
    ]

    operations = [
        migrations.RunPython(apply_paddleocr_configs, reverse_paddleocr_configs),
    ]
