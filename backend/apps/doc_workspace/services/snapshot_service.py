"""版本留底：覆盖之前先存一份旧内容。

调用点只有两处（都是「能静默毁掉内容」的写路径）：

| 写路径 | 调用点 |
|---|---|
| 编辑器保存回写（DS status=2/6） | `apps/onlyoffice/services/domain_registry._adopt_edited` |
| AI 落笔（修订 / 审查结论） | `apps/doc_workspace/services/write_service.apply_span` |

**为什么不塞进 `BoundFolderBrowseService.save_file_content`**：那是 `apps/core`
的通用基础设施，让它反向 import 业务 app 会把分层搞乱（core 不依赖任何 apps.*）。
代价是「新增写路径必须自己记得快照」——用 `tests/ci/structure/` 里的结构测试
兜住：`apps/doc_workspace` 下任何写盘调用都必须经过本模块。

## 回滚也是可回滚的

`restore()` 的动作是「先把**当前**内容快照一份（reason=restore），再写回旧字节」。
所以律师点错回滚版本，再点一次另一个版本就能救回来——不需要额外的确认流程。
"""

from __future__ import annotations

import hashlib
import logging
from io import BytesIO
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, connection, transaction
from django.db.models import Max

from apps.core.filesystem.upload_paths import MediaEntity

from ..models import ActorKind, DocSnapshot, SnapshotReason

logger = logging.getLogger(__name__)

#: seq 冲突重试次数。
#:
#: PG 下靠咨询锁串行化，重试基本用不上；非 PG（本地 sqlite 跑单测）没有
#: 咨询锁，只能靠唯一约束 + 重试兜底。
_SEQ_RETRY = 3


def _lock_key(kind: str, owner_id: int, subpath: str) -> int:
    """(kind, owner_id, subpath) → 一个稳定的 64 位锁键。

    **为什么用文件坐标而不是全局单一锁**：不同文件的快照应该并行，只有同一份
    文件的并发覆写需要串行。
    """
    digest = hashlib.sha256(f"{kind}:{owner_id}:{subpath}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _acquire_seq_lock(kind: str, owner_id: int, subpath: str) -> None:
    """拿事务级咨询锁，把「算 max+1 并插入」串行化。

    **不能用 `select_for_update`**：还没有父行可锁，聚合查询也拿不到行锁；
    六七个并发请求会同时读到同一个 max，于是全部算出同一个 seq，唯一约束
    集体报错（真机测过：3 次重试全部用尽）。

    必须在 `transaction.atomic()` **内**调用：`pg_advisory_xact_lock` 是事务级的，
    没有事务包着等于立刻释放。
    """
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_lock_key(kind, owner_id, subpath)])


def _blob_path(sha256: str) -> str:
    """内容寻址路径：同内容永远同一路径，天然去重。"""
    return f"{MediaEntity.DOC_SNAPSHOTS}/{sha256[:2]}/{sha256}.docx"


def _store_blob(data: bytes, sha256: str) -> str:
    """把字节存进 MEDIA（幂等）。返回 storage 路径。"""
    path = _blob_path(sha256)
    if default_storage.exists(path):
        return path
    saved = default_storage.save(path, ContentFile(data))
    if saved != path:
        # 极小概率的并发：另一个请求刚好先写了同名文件，storage 给了个新名字。
        # 内容一样，用它的路径即可（去重不以路径形状为准，以 sha 为准）。
        logger.info("快照 blob 命名碰撞，改用 storage 返回的路径: %s", saved)
    return str(saved)


def _next_seq(kind: str, owner_id: int, subpath: str) -> int:
    agg = DocSnapshot.objects.filter(owner_kind=kind, owner_id=owner_id, subpath=subpath).aggregate(m=Max("seq"))
    return int(agg["m"] or 0) + 1


def capture(
    *,
    kind: str,
    owner_id: int,
    subpath: str,
    data: bytes,
    reason: str,
    source_mtime: float | None = None,
    actor_kind: str = ActorKind.UNKNOWN,
    actor_id: int | None = None,
) -> DocSnapshot:
    """把 `data` 存成该文件的下一版快照。

    同 sha 只存一份 blob，但**每次调用都会新增一行**——seq 连续是时间线可信的前提，
    去重只发生在存储层。
    """
    sha = hashlib.sha256(data).hexdigest()
    storage_path = _store_blob(data, sha)

    last_error: Exception | None = None
    for attempt in range(_SEQ_RETRY):
        try:
            with transaction.atomic():
                _acquire_seq_lock(kind, owner_id, subpath)
                seq = _next_seq(kind, owner_id, subpath)
                return DocSnapshot.objects.create(
                    owner_kind=kind,
                    owner_id=owner_id,
                    subpath=subpath,
                    seq=seq,
                    sha256=sha,
                    size=len(data),
                    source_mtime=source_mtime,
                    storage_path=storage_path,
                    reason=reason,
                    actor_kind=actor_kind,
                    actor_id=actor_id,
                )
        except IntegrityError as exc:  # 唯一约束撞车 = 并发覆写，重算 seq
            last_error = exc
            logger.warning("快照 seq 冲突，第 %d 次重试: %s/%s/%s", attempt + 1, kind, owner_id, subpath)

    # 重试用尽仍然冲突：宁可抛出去让上层拒绝这次覆盖，也不要静默不记录
    raise RuntimeError(f"无法为 {subpath} 分配快照版本号（并发写入过多）") from last_error


def list_snapshots(*, kind: str, owner_id: int, subpath: str, limit: int = 50) -> list[DocSnapshot]:
    """该文件的快照时间线（新→旧）。"""
    return list(
        DocSnapshot.objects.filter(owner_kind=kind, owner_id=owner_id, subpath=subpath).order_by("-seq")[:limit]
    )


def latest(*, kind: str, owner_id: int, subpath: str) -> DocSnapshot | None:
    return DocSnapshot.objects.filter(owner_kind=kind, owner_id=owner_id, subpath=subpath).order_by("-seq").first()


def find_by_seq(*, kind: str, owner_id: int, subpath: str, seq: int) -> DocSnapshot | None:
    return DocSnapshot.objects.filter(owner_kind=kind, owner_id=owner_id, subpath=subpath, seq=seq).first()


def read_bytes(snapshot: DocSnapshot) -> bytes:
    """读回快照字节（并校验 sha——存储被动过就要立刻炸出来，不能悄悄回滚错内容）。"""
    with default_storage.open(snapshot.storage_path, "rb") as fh:
        data: bytes = fh.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != snapshot.sha256:
        raise ValueError(f"快照内容已损坏: {snapshot.id} 期望 {snapshot.sha256[:12]} 实际 {actual[:12]}")
    return data


def restore(
    *,
    kind: str,
    owner_id: int,
    subpath: str,
    seq: int,
    user: Any = None,
    org_access: Any = None,
) -> dict[str, Any]:
    """把该文件回滚到第 `seq` 版。

    顺序不能反：**先把当前内容快照一份**，再写旧字节。反过来一旦中途失败，
    当前版本就永远没了——回滚动作本身变成事故。
    """
    from . import write_service

    target = find_by_seq(kind=kind, owner_id=owner_id, subpath=subpath, seq=seq)
    if target is None:
        return {"restored": False, "reason": f"找不到第 {seq} 版快照"}

    current = write_service.read_bytes(kind=kind, owner_id=owner_id, subpath=subpath, user=user, org_access=org_access)
    snapshot = capture(
        kind=kind,
        owner_id=owner_id,
        subpath=subpath,
        data=current,
        reason=SnapshotReason.RESTORE,
        actor_kind=ActorKind.HUMAN if user is not None else ActorKind.UNKNOWN,
        actor_id=getattr(user, "pk", None),
    )

    restored_bytes = read_bytes(target)
    write_service.write_bytes(
        kind=kind,
        owner_id=owner_id,
        subpath=subpath,
        data=restored_bytes,
        user=user,
        org_access=org_access,
    )
    logger.info(
        "已回滚到历史版本: %s/%s/%s seq=%d（回滚前内容存为 v%d）",
        kind,
        owner_id,
        subpath,
        seq,
        snapshot.seq,
    )
    return {
        "restored": True,
        "seq": seq,
        "sha256": target.sha256,
        # 回滚前那一版的新 seq：律师想撤销这次回滚时用它
        "previous_seq": snapshot.seq,
    }


def read_stream_for_download(snapshot: DocSnapshot) -> BytesIO:
    """下载用：一次读进内存（合同 docx 量级，不值得分块）。"""
    return BytesIO(read_bytes(snapshot))
