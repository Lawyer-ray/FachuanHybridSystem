"""冲红搬移子系统：发票在合同文件夹里的落点（`<发票目录>/已冲红/`）与搬运。

## 为什么直接用 pathlib 而不走 ``ContractFolderBrowseService``

浏览服务只提供 ``rename``（同目录改名）/ ``copy_entry`` + ``delete_entry``（两步，
中间失败就留下两份或零份）。本动作要求“要么原位要么位置”，而且调用方手里已经有
绑定根的绝对路径，查一次目录列表就能校验“源在已冲红 / 目标不在已冲红”，然后
``Path.replace`` 在同文件系统上一步完成——比“复制 + 软删”少一半失败面。

ACL 仍走合同行级鉴权（宿主 ``InvoiceFileService.ensure_contract_access``），路径合法
仍用 ``Path.relative_to`` 校验不越出绑定根（等价于 ``is_within_root``），不新开豁口。

## 为什么入口要注入宿主服务

两个搬移动作的鉴权口径必须与发票落库完全一致，所以这里不自己拼 ``ContractAccessPolicy``
调用，而是把宿主服务实例传进来，只调它的 ``ensure_contract_access`` 一个方法——
这样本模块无需 import 宿主模块（依赖方向只能是「宿主 → 本模块」），也不会有第二份
鉴权实现。

## 目录/命名约定是跨模块契约

``VOIDED_DIR_NAME`` 与 ``VOIDED_NAME_MARKER`` 同时被闸 2（文件夹扫描）与闸 3（归档材料）
用作“作废票”的识别依据，改值必须同步改那两处（见 ``invoice_file_service`` 模块 docstring）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.db import transaction

logger = logging.getLogger("apps.contracts")

#: 冲红隔离目录名（挂在发票目录下）。闸 2（文件夹扫描）与闸 3（归档材料）都按这个名字 /
#: 文件名里的「红字开具」识别作废票，改这里必须同步改那两处
VOIDED_DIR_NAME = "已冲红"
#: 红票文件名的尾部标记（`YYYYMMDD红字开具.pdf`）。归档闸 3 只能靠它判断作废票
VOIDED_NAME_MARKER = "红字开具"
#: 合同文件夹里发票目录的名字特征（`发票` / `3-发票` / `1-律师资料/3-发票`）
INVOICE_DIR_NAME = "发票"


def _invoice_contract_id(invoice: Any) -> int | None:
    """发票归属的合同：挂收款时跟收款走，先开票后付款时直接挂合同。"""
    contract_id = getattr(invoice, "contract_id", None)
    if contract_id:
        return int(contract_id)
    payment = getattr(invoice, "payment", None) if getattr(invoice, "payment_id", None) else None
    payment_contract_id = getattr(payment, "contract_id", None)
    return int(payment_contract_id) if payment_contract_id else None


def _skip_reason(exc: Exception) -> str:
    return str(getattr(exc, "message", "") or exc or "无法写入合同文件夹")


def _ensure_voided_dir(service: Any, contract_id: int, invoice_dir: str, access: dict[str, Any]) -> str:
    """`<发票目录>/已冲红/` 的 subpath，不存在则建（**按需创建**）。

    空目录在 Finder 里是噪声，也不该污染律所模板目录，所以只在真要写入时建。
    并发下另一次冲红已建好同名目录时 mkdir 会报“同名项目已存在”，直接当已存在处理。
    """
    target = f"{invoice_dir}/{VOIDED_DIR_NAME}" if invoice_dir else VOIDED_DIR_NAME
    try:
        entries = service.list_entries(owner_id=contract_id, subpath=invoice_dir, **access)
    except Exception:
        entries = {}
    for folder in entries.get("folders") or []:
        if isinstance(folder, dict) and str(folder.get("name") or "").strip() == VOIDED_DIR_NAME:
            return str(folder.get("subpath") or target)
    try:
        created = service.mkdir(owner_id=contract_id, subpath=invoice_dir, name=VOIDED_DIR_NAME, **access)
        return str(created.get("subpath") or target)
    except Exception:
        logger.info("invoice_voided_dir_mkdir_skipped", extra={"subpath": target})
        return target


@transaction.atomic
def move_invoice_to_voided(
    invoice_file_service: Any,
    *,
    invoice_id: int,
    user: Any | None = None,
    org_access: dict[str, Any] | None = None,
    perm_open_access: bool = False,
) -> str:
    """把原票移进 `<发票目录>/已冲红/` 并写回 ``folder_subpath``，返回新 subpath。

    **移动而非复制**：原票从发票目录移出，不允许“根目录一份 + 已冲红一份”；
    ``folder_subpath`` 是撤销时确定位置的唯一依据，不许出现两份。
    未镜像到合同文件夹（``folder_subpath`` 为空）时返回空串（media 副本仍在）。
    """
    return _relocate_voided(
        invoice_file_service,
        invoice_id,
        to_voided=True,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


@transaction.atomic
def move_invoice_back_from_voided(
    invoice_file_service: Any,
    *,
    invoice_id: int,
    user: Any | None = None,
    org_access: dict[str, Any] | None = None,
    perm_open_access: bool = False,
) -> str:
    """撤销时把原票从 `已冲红/` 移回发票目录，并写回 ``folder_subpath``。

    整组撤销必须移回：半截状态（红票删了、原票还在 `已冲红/`）是比错账更难查的
    东西。不在 `已冲红/` 里时原样返回旧 subpath（幂等，可重入）。
    """
    return _relocate_voided(
        invoice_file_service,
        invoice_id,
        to_voided=False,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


def _relocate_voided(
    invoice_file_service: Any,
    invoice_id: int,
    *,
    to_voided: bool,
    user: Any | None,
    org_access: dict[str, Any] | None,
    perm_open_access: bool,
) -> str:
    """冲红目录与发票目录之间的文件搬运（两个公开函数的共用实现）。

    **为什么直接用 pathlib 而不走 ``ContractFolderBrowseService``**：浏览服务只提供
    ``rename``（同目录改名）/ ``copy_entry`` + ``delete_entry``（两步，中间失败就留下
    两份或零份）。本动作要求“要么原位要么位置”，而且我们手里已经有绑定根的绝对路径，
    查一次目录列表就能校验“源在已冲红 / 目标不在已冲红”，然后 ``Path.replace``
    在同文件系统上一步完成——比“复制 + 软删”少一半失败面。

    ACL 仍走合同行级鉴权（``ensure_contract_access``），路径合法仍用 ``Path.relative_to``
    校验不越出绑定根（等价于 ``is_within_root``），不新开豁口。
    """
    from apps.contracts.models import Invoice
    from apps.core.exceptions import NotFoundError, ValidationException

    try:
        invoice = Invoice.objects.select_related("payment__contract", "contract").get(pk=invoice_id)
    except Invoice.DoesNotExist:
        raise NotFoundError(message="发票不存在", code="INVOICE_NOT_FOUND") from None

    contract_id = _invoice_contract_id(invoice)
    invoice_file_service.ensure_contract_access(
        contract_id, user=user, org_access=org_access, perm_open_access=perm_open_access
    )
    subpath = str(getattr(invoice, "folder_subpath", "") or "")
    if contract_id is None or not subpath:
        return subpath

    from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

    access: dict[str, Any] = {"user": user, "org_access": org_access, "perm_open_access": perm_open_access}
    service = ContractFolderBrowseService()
    try:
        root = service._local_root(contract_id)  # 子类钩子，取绑定根是唯一来源
    except Exception as exc:  # 未绑定 / 云存储 / 目录不可达：不阻断裁定，folder_subpath 保持原值
        logger.info(
            "invoice_folder_relocate_root_unreachable",
            extra={"contract_id": contract_id, "reason": _skip_reason(exc)},
        )
        return subpath
    source = root / subpath
    if not source.is_file():
        logger.info("invoice_folder_relocate_source_missing", extra={"contract_id": contract_id, "subpath": subpath})
        return subpath

    # `Path("")` 是 `Path(".")`，直接当父目录会把文件移到 "x.pdf/已冲红/" 这种鬼路径下。
    # 发票直接落在绑定根时 parent 为空串，这里显式收敛成 root。
    parent_dir = root / Path(subpath).parent
    if to_voided:
        target_dir = parent_dir / VOIDED_DIR_NAME
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        # 撤回到发票目录：`<发票目录>/已冲红/x.pdf` → `<发票目录>/x.pdf`。
        # 不在已冲红里时 parent 就是发票目录本身，不动文件（幂等）。
        in_voided = parent_dir.name == VOIDED_DIR_NAME
        target_dir = parent_dir.parent if in_voided else parent_dir
    if not target_dir.is_dir():
        raise ValidationException(message="发票目录不存在，无法移动发票", errors={"subpath": subpath})

    target = target_dir / source.name
    if target.is_file() and target.resolve() == source.resolve():
        return subpath
    if target.exists():
        # 同名不同件：加序号，宁可多一个后缀也不覆盖任何一份原件。
        # 同件（上一轮已移完但 folder_subpath 没落库）时 replace 不会重复写内容。
        target = service._unique_destination(target_dir, source.name)
    source.replace(target)  # 同一文件系统内的原子改名（跨目录就是移动）

    try:
        new_subpath = target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        raise ValidationException(message="发票移动目标越界", errors={"subpath": subpath}) from None

    Invoice.objects.filter(pk=invoice.pk).update(folder_subpath=new_subpath)
    logger.info(
        "invoice_folder_voided_relocated",
        extra={
            "contract_id": contract_id,
            "invoice_id": invoice.pk,
            "from": subpath,
            "to": new_subpath,
            "to_voided": to_voided,
        },
    )
    return new_subpath


def _locate_invoice_dir(service: Any, contract_id: int, access: dict[str, Any]) -> str:
    """在绑定文件夹两层内找发票目录；找不到就在顶层建 `发票/`。返回子目录 subpath。"""
    root = service.list_entries(owner_id=contract_id, subpath="", **access)

    def _dirs(entries: dict[str, Any]) -> list[dict[str, Any]]:
        return [f for f in (entries.get("folders") or []) if isinstance(f, dict) and f.get("name")]

    l1_dirs = _dirs(root)
    for folder in l1_dirs:
        if _is_invoice_dir(str(folder["name"])):
            return str(folder.get("subpath") or folder["name"])

    # 第二层：`1-律师资料/3-发票` 这类嵌套
    for folder in l1_dirs:
        try:
            entries = service.list_entries(
                owner_id=contract_id, subpath=str(folder.get("subpath") or folder["name"]), **access
            )
        except Exception as exc:
            logger.info("invoice_folder_walk_skipped", extra={"folder": str(folder["name"]), "reason": str(exc)})
            continue
        for sub in _dirs(entries):
            if _is_invoice_dir(str(sub["name"])):
                return str(sub.get("subpath") or f"{folder['name']}/{sub['name']}")

    try:
        service.mkdir(owner_id=contract_id, subpath="", name=INVOICE_DIR_NAME, **access)
    except Exception as exc:
        # 并发下另一张发票已建好同名目录 → 视为已存在，继续写文件
        logger.info("invoice_folder_mkdir_skipped", extra={"reason": str(exc)})
    return INVOICE_DIR_NAME


def _is_invoice_dir(name: str) -> bool:
    """`发票` / `3-发票` 认；`发票领取台账` 这类记录性目录不误认（要求以「发票」结尾）。"""
    cleaned = name.strip()
    return cleaned.endswith(INVOICE_DIR_NAME) and len(cleaned) <= 12
