"""清洗当事人证件类型与主体类型不匹配的历史脏数据。

背景（2026-11-06 实爆）：`ClientIdentityDoc.clean()` 于 v27.2.6 随模型新建时引入，
按主体类型限制可用证件类型（自然人有身份证/护照等，法人只有营业执照/法人身份证），
但当时没有配套数据迁移，存量脏行因此永久卡死在 admin：

- admin inline 的每一行（**包括勾了「删除」的行**）都会先跑 Model.clean()，
  DELETE 标记只在 save_existing_objects() 阶段生效，赶不上校验 → 保存和删除双双失败；
- 就算改证件类型也救不回来，因为 (client, doc_type) 有唯一约束，合法值槽位可能已被占。

本迁移按「不丢文件」原则处理：
1. 脏行的证件类型能推断出正确归属时（法人主体持自然人证件 → 法人证件），
   若目标类型槽位空闲则直接改类型；若目标槽位已被占且目标行**没有真实文件**
   而脏行有，则把文件路径迁移给目标行后删除脏行；
2. 无法安全推断的脏行只做记录，不擅自删除。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import migrations

logger = logging.getLogger("apps.client")

# 与 apps.client.models.identity_doc.IdentityDocType 保持一致（迁移内不 import 模型，防后续改名脆断）
NATURAL_DOC_TYPES = frozenset({"id_card", "passport", "hk_macao_permit", "residence_permit", "household_register"})
LEGAL_DOC_TYPES = frozenset({"business_license", "legal_rep_id_card"})

# 法人主体持有自然人证件时的归并目标
LEGAL_FALLBACK = {
    "id_card": "legal_rep_id_card",
    "passport": "legal_rep_id_card",
    "hk_macao_permit": "legal_rep_id_card",
    "residence_permit": "legal_rep_id_card",
    "household_register": "business_license",
}
# 自然人主体持有法人证件时的归并目标
_NATURAL_FALLBACK = {"business_license": "id_card", "legal_rep_id_card": "id_card"}


def _file_exists(file_path: str | None) -> bool:
    if not file_path:
        return False
    root = Path(str(getattr(settings, "MEDIA_ROOT", "")))
    return (root / file_path).exists()


def _is_valid(client_type: str | None, doc_type: str | None) -> bool:
    """判断证件类型是否适用于主体类型；无法判定时返回 True（不擅自处理）。"""
    if not client_type or not doc_type:
        return True
    if client_type == "natural":
        return doc_type in NATURAL_DOC_TYPES
    if client_type in {"legal", "non_legal_org"}:
        return doc_type in LEGAL_DOC_TYPES
    # 未知主体类型不做判定，交给人工
    return True


def fix_mismatched_identity_docs(apps: Any, schema_editor: Any) -> None:
    """把证件类型与当事人主体类型不匹配的脏行归并到合法类型。"""
    Client = apps.get_model("client", "Client")
    ClientIdentityDoc = apps.get_model("client", "ClientIdentityDoc")

    bad = []
    for doc in ClientIdentityDoc.objects.select_related("client").iterator():
        client_type = getattr(doc.client, "client_type", None)
        if not _is_valid(client_type, doc.doc_type):
            bad.append(doc)

    if not bad:
        return

    for doc in bad:
        client_type = doc.client.client_type
        fallback_map = LEGAL_FALLBACK if client_type in {"legal", "non_legal_org"} else _NATURAL_FALLBACK
        target_type = fallback_map.get(doc.doc_type)
        if target_type is None:
            logger.warning(
                "跳过无法自动推断归属的证件行",
                extra={"doc_id": doc.pk, "client_id": doc.client_id, "doc_type": doc.doc_type},
            )
            continue

        existing = (
            ClientIdentityDoc.objects.filter(client_id=doc.client_id, doc_type=target_type).exclude(pk=doc.pk).first()
        )

        if existing is None:
            doc.doc_type = target_type
            doc.save(update_fields=["doc_type"])
            logger.info(
                "证件类型已归并到合法值",
                extra={"doc_id": doc.pk, "client_id": doc.client_id, "to": target_type},
            )
            continue

        # 目标槽位已被占：只有「目标行没有真实文件、脏行有」时才搬文件过去，避免丢文件
        if _file_exists(doc.file_path) and not _file_exists(existing.file_path):
            # 顺序敏感（两个唯一约束夹着）：
            #   1. 直接改 dirty 行的 doc_type 会撞 uniq_clientidentitydoc_client_doctype（槽位已占）；
            #   2. 先把路径写给 existing 会撞 uniq_clientidentitydoc_client_file_path（doc 还持有它）。
            # 唯一安全顺序：先删 doc 释放路径 → 再把路径写到 existing。
            keep_path = doc.file_path
            doc.delete()
            existing.file_path = keep_path
            existing.save(update_fields=["file_path"])
            logger.info(
                "文件路径已迁移到既有证件行并删除重复行",
                extra={"doc_id": doc.pk, "keep_id": existing.pk, "client_id": doc.client_id},
            )
        elif not doc.file_path:
            # 脏行没有文件，纯占位垃圾，直接删
            doc.delete()
            logger.info("已删除无文件的重复证件行", extra={"doc_id": doc.pk, "keep_id": existing.pk})
        else:
            logger.warning(
                "证件行无处归并（目标槽位已有文件），保留待人工处理",
                extra={"doc_id": doc.pk, "client_id": doc.client_id, "conflict_id": existing.pk},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("client", "0017_alter_clientidentitydoc_file_path"),
    ]

    operations = [
        migrations.RunPython(fix_mismatched_identity_docs, migrations.RunPython.noop),
    ]
