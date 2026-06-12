"""迁移 PaddleOCR 配置：删除旧 API 端点，新增 v2 Job API 端点

旧版 API（同步，各模型独立 URL）→ 新版 v2 API（异步 Job，统一 URL）

删除:
- PADDLEOCR_OCR_API_URL
- PADDLEOCR_VL_API_URL
- PADDLEOCR_VL15_API_URL

新增:
- PADDLEOCR_JOB_API_URL

更新:
- PADDLEOCR_API_MODEL: 默认值 pp_ocrv5 → PP-OCRv6，描述更新
- PADDLEOCR_API_TOKEN: 描述更新 (token → bearer)
"""

from django.db import migrations


def migrate_paddleocr_configs(apps, schema_editor):  # pragma: no cover
    """执行 PaddleOCR 配置迁移"""
    SystemConfig = apps.get_model("core", "SystemConfig")

    # ── 1. 删除旧配置项 ──────────────────────────────────
    old_keys = [
        "PADDLEOCR_OCR_API_URL",
        "PADDLEOCR_VL_API_URL",
        "PADDLEOCR_VL15_API_URL",
    ]
    deleted, _ = SystemConfig.objects.filter(key__in=old_keys).delete()
    print(f"  删除旧配置: {deleted} 个 ({', '.join(old_keys)})")

    # ── 2. 新增 PADDLEOCR_JOB_API_URL ───────────────────
    obj, created = SystemConfig.objects.update_or_create(
        key="PADDLEOCR_JOB_API_URL",
        defaults={
            "category": "ocr",
            "description": "PaddleOCR v2 异步 Job API 地址（所有模型共用）",
            "value": "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs",
            "is_secret": False,
        },
    )
    print(f"  {'创建' if created else '更新'}: PADDLEOCR_JOB_API_URL")

    # ── 3. 更新 PADDLEOCR_API_MODEL ─────────────────────
    obj, created = SystemConfig.objects.update_or_create(
        key="PADDLEOCR_API_MODEL",
        defaults={
            "category": "ocr",
            "description": (
                "PaddleOCR API 模型选择（"
                "PP-OCRv6=纯文字OCR-适合证件/快递单号/简单文字提取, "
                "PaddleOCR-VL-1.6=版面分析+OCR-适合复杂文档/合同/法律文书）"
            ),
            "value": "PP-OCRv6",
            "is_secret": False,
        },
    )
    print(f"  {'创建' if created else '更新'}: PADDLEOCR_API_MODEL")

    # ── 4. 更新 PADDLEOCR_API_TOKEN 描述 ────────────────
    obj, created = SystemConfig.objects.update_or_create(
        key="PADDLEOCR_API_TOKEN",
        defaults={
            "category": "ocr",
            "description": "PaddleOCR API Token（Authorization: bearer {TOKEN}）",
            "is_secret": True,
        },
    )
    print(f"  {'创建' if created else '更新'}: PADDLEOCR_API_TOKEN")


def reverse_migrate(apps, schema_editor):  # pragma: no cover
    """回滚：删除新配置，恢复旧配置"""
    SystemConfig = apps.get_model("core", "SystemConfig")

    # 删除新增的配置
    SystemConfig.objects.filter(key="PADDLEOCR_JOB_API_URL").delete()

    # 恢复旧配置
    old_configs = [
        {
            "key": "PADDLEOCR_OCR_API_URL",
            "category": "ocr",
            "description": "PaddleOCR OCR 接口地址（PP-OCRv5 / PP-StructureV3 共用）",
            "value": "https://ndvex8b5vcd0teg7.aistudio-app.com/ocr",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_VL_API_URL",
            "category": "ocr",
            "description": "PaddleOCR-VL 版面分析接口地址",
            "value": "https://h8d58fh8mfw84cj4.aistudio-app.com/layout-parsing",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_VL15_API_URL",
            "category": "ocr",
            "description": "PaddleOCR-VL-1.5 高精度版面分析接口地址",
            "value": "https://k4j5n7j1afr2j9p5.aistudio-app.com/layout-parsing",
            "is_secret": False,
        },
    ]
    for cfg in old_configs:
        SystemConfig.objects.update_or_create(key=cfg["key"], defaults=cfg)

    # 恢复旧模型默认值
    SystemConfig.objects.filter(key="PADDLEOCR_API_MODEL").update(
        description=(
            "PaddleOCR API 模型选择（"
            "pp_ocrv5=纯文字OCR-适合证件/快递单号/简单文字提取, "
            "pp_structure_v3=文档结构化-适合表格/版面分析, "
            "paddleocr_vl=版面分析+OCR-适合复杂文档/合同, "
            "paddleocr_vl_1_5=高精度版面分析-适合法律文书/密集排版文档）"
        ),
        value="pp_ocrv5",
    )

    # 恢复旧 token 描述
    SystemConfig.objects.filter(key="PADDLEOCR_API_TOKEN").update(
        description="PaddleOCR API Token（Authorization: token {TOKEN}）",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_add_document_parsing_category"),
    ]

    operations = [
        migrations.RunPython(migrate_paddleocr_configs, reverse_migrate),
    ]
