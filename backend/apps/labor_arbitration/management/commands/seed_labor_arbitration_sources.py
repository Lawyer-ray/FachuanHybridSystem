"""写入佛山 6 个区县的劳动仲裁文书来源（幂等）。"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.labor_arbitration.models import ArbitrationDocumentSource, District

SOURCES = [
    {
        "name": "佛山市直仲裁文书",
        "district": District.SHI_ZHI,
        "list_url": "https://hrss.foshan.gov.cn/ztzl/ldgxytjzc/zcwsgk/szzcws/",
        "category_id": 42087,
    },
    {
        "name": "禅城区仲裁文书",
        "district": District.CHAN_CHENG,
        "list_url": "https://hrss.foshan.gov.cn/ztzl/ldgxytjzc/zcwsgk/ccqzcws/",
        "category_id": 41998,
    },
    {
        "name": "南海区仲裁文书",
        "district": District.NAN_HAI,
        "list_url": "https://hrss.foshan.gov.cn/ztzl/ldgxytjzc/zcwsgk/nhqzcws/",
        "category_id": 41999,
    },
    {
        "name": "顺德区仲裁文书",
        "district": District.SHUN_DE,
        "list_url": "https://hrss.foshan.gov.cn/ztzl/ldgxytjzc/zcwsgk/sdqzcws/",
        "category_id": 42000,
    },
    {
        "name": "高明区仲裁文书",
        "district": District.GAO_MING,
        "list_url": "https://hrss.foshan.gov.cn/ztzl/ldgxytjzc/zcwsgk/gmqzcws/",
        "category_id": 42001,
    },
    {
        "name": "三水区仲裁文书",
        "district": District.SAN_SHUI,
        "list_url": "https://hrss.foshan.gov.cn/ztzl/ldgxytjzc/zcwsgk/ssqzcws/",
        "category_id": 42002,
    },
]


class Command(BaseCommand):
    help = "写入佛山各区县劳动仲裁文书来源（幂等，已存在则跳过）"

    def handle(self, *args: object, **options: object) -> None:
        created = 0
        updated = 0
        for spec in SOURCES:
            obj, is_new = ArbitrationDocumentSource.objects.get_or_create(
                list_url=spec["list_url"],
                defaults={
                    "name": spec["name"],
                    "district": spec["district"],
                    "category_id": spec.get("category_id"),
                },
            )
            if is_new:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"已创建: {obj.name}"))
            else:
                # 幂等回填 category_id
                if obj.category_id != spec.get("category_id"):
                    obj.category_id = spec.get("category_id")
                    obj.save(update_fields=["category_id"])
                    updated += 1
                self.stdout.write(f"已存在: {obj.name}")
        self.stdout.write(self.style.SUCCESS(f"完成，新建 {created} 个来源，更新 category_id {updated} 个。"))
