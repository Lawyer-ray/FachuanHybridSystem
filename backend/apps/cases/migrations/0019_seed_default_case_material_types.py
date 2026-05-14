from __future__ import annotations

from django.db import migrations


PARTY_TYPES = (
    "起诉状",
    "答辩状",
    "证据材料",
    "身份材料",
    "授权委托材料",
    "保全材料",
    "执行材料",
    "其它材料",
)

NON_PARTY_TYPES = (
    "法院文书",
    "送达材料",
    "回执材料",
    "裁定/决定文书",
    "其它材料",
)


def seed_default_material_types(apps, schema_editor):
    CaseMaterialType = apps.get_model("cases", "CaseMaterialType")
    for category, names in (("party", PARTY_TYPES), ("non_party", NON_PARTY_TYPES)):
        for name in names:
            CaseMaterialType.objects.get_or_create(
                law_firm=None,
                category=category,
                name=name,
                defaults={"is_active": True},
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0018_merge_20260512_0017_cases"),
    ]

    operations = [
        migrations.RunPython(seed_default_material_types, noop_reverse),
    ]
