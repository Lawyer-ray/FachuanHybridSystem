"""Migrate archive_item_code from 4.x.x format to nl_/lt_/cr_ format.

The old code format (e.g. "4.2.1") was a display-oriented sequence number.
The new format (e.g. "lt_1") is a stable identifier; display numbering is
handled by CSS counters on the frontend.
"""

from django.db import migrations

# Old code → New code mapping
_CODE_MAPPING: dict[str, str] = {
    # Non-litigation (4.1.x → nl_x)
    "4.1.1": "nl_1",
    "4.1.2": "nl_2",
    "4.1.3": "nl_3",
    "4.1.4": "nl_4",
    "4.1.5": "nl_5",
    "4.1.6": "nl_6",
    "4.1.7": "nl_7",
    "4.1.8": "nl_8",
    "4.1.9": "nl_9",
    "4.1.10": "nl_10",
    "4.1.11": "nl_11",
    # Litigation (4.2.x → lt_x)
    "4.2.1": "lt_1",
    "4.2.2": "lt_2",
    "4.2.3": "lt_3",
    "4.2.4": "lt_4",
    "4.2.5": "lt_5",
    "4.2.5.1": "lt_6",
    "4.2.6": "lt_7",
    "4.2.7": "lt_8",
    "4.2.8": "lt_9",
    "4.2.9": "lt_10",
    "4.2.10": "lt_11",
    "4.2.11": "lt_12",
    "4.2.12": "lt_13",
    "4.2.13": "lt_14",
    "4.2.14": "lt_15",
    "4.2.15": "lt_16",
    "4.2.16": "lt_17",
    "4.2.17": "lt_18",
    "4.2.18": "lt_19",
    # Criminal (4.3.x → cr_x)
    "4.3.1": "cr_1",
    "4.3.2": "cr_2",
    "4.3.3": "cr_3",
    "4.3.4": "cr_4",
    "4.3.5": "cr_5",
    "4.3.6": "cr_6",
    "4.3.7": "cr_7",
    "4.3.8": "cr_8",
    "4.3.9": "cr_9",
    "4.3.10": "cr_10",
    "4.3.11": "cr_11",
    "4.3.12": "cr_12",
    "4.3.13": "cr_13",
    "4.3.14": "cr_14",
    "4.3.15": "cr_15",
    "4.3.16": "cr_16",
    "4.3.17": "cr_17",
}


def migrate_archive_item_codes_forwards(apps, schema_editor):
    FinalizedMaterial = apps.get_model("contracts", "FinalizedMaterial")
    for old_code, new_code in _CODE_MAPPING.items():
        FinalizedMaterial.objects.filter(archive_item_code=old_code).update(
            archive_item_code=new_code
        )


def migrate_archive_item_codes_reverse(apps, schema_editor):
    FinalizedMaterial = apps.get_model("contracts", "FinalizedMaterial")
    reverse_mapping = {v: k for k, v in _CODE_MAPPING.items()}
    for new_code, old_code in reverse_mapping.items():
        FinalizedMaterial.objects.filter(archive_item_code=new_code).update(
            archive_item_code=old_code
        )


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0014_material_category_archive_additions"),
    ]

    operations = [
        migrations.RunPython(
            migrate_archive_item_codes_forwards,
            migrate_archive_item_codes_reverse,
        ),
    ]
