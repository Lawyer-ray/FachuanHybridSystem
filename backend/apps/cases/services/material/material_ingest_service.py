"""材料归案：把客户给的文件夹变成「案件材料 + 解析任务」，让起草拿得到正文。

## 为什么需要这一步

起草链的输入只有两种：案件实体上的结构化字段，和 `CaseMaterial` 指向的解析结果。
真机（案卷 489）里材料全在律师的本地文件夹里，库里 `materials=[]` —— 于是
`assess` 只能如实回答「材料一项都没有」，起草也就无从谈起。缺的不是能力，是**入档**。

## 三个协议

1. **一条汇总日志 + N 个附件**：`CaseMaterial.source_attachment` 是 OneToOne 到
   `CaseLogAttachment`，而附件必须挂在某个 `CaseLog` 上。所以一次归案建一条日志
   （内容写清来源目录），每个文件一个附件、一条材料，**不再造第二套附件模型**。
2. **解析结果按 id 绑在材料上**：`CaseMaterial.parsing_task` 是本次新增的 FK。
   原来只能按文件名匹配解析任务，文件名会撞；有了 FK，起草取的是「这条材料那次解析」。
3. **解析失败不影响归案**：文件已经进库、材料已经登记，只是 `parsing_task` 为空。
   把已上传的文件回滚掉，比「解析没跑成」更难解释。

## 什么时候同步解析

`parse_now=True`（默认）用 `DocumentParserService` 就地跑完——律师点了「归案」就该
立刻能在起草里看到内容；批量导入大卷宗时传 `False`，交给任务队列慢慢跑。
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from apps.cases.models.log import CaseLog, CaseLogAttachment
from apps.cases.models.material import CaseMaterial, CaseMaterialCategory, CaseMaterialSide

logger = logging.getLogger(__name__)

#: 归案日志的默认内容：律师在案件日志里看到的就是这一句 + 附件列表
DEFAULT_LOG_CONTENT = "材料归案：从本地文件夹导入"

#: 单个文件的解析上限。手机拍照件单页 2~3 MiB，50 MiB 已覆盖整本扫描件；
#: 再大就是误选（视频、压缩包），归案时报错比让它占满解析预算好。
MAX_FILE_BYTES = 50 * 1024 * 1024

#: 只归这些扩展名：其余文件（xlsx/zip/图片）解析链拿不到正文，登记了也只是噪音
SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".doc", ".txt", ".md"})

_SKIP_NAMES = frozenset({".DS_Store", "Thumbs.db", "out.txt"})


def ingest_directory(
    *,
    case_id: int,
    directory: str | Path,
    actor: Any = None,
    content: str = DEFAULT_LOG_CONTENT,
    material_type_name: str = "客户提供材料",
    category: str = CaseMaterialCategory.PARTY,
    side: str = CaseMaterialSide.OUR,
    parse_now: bool = True,
    backend: str = "auto",
) -> list[CaseMaterial]:
    """把一个目录下的受支持文件归案：附件 + 材料 + 解析任务（幂等）。

    幂等口径：同一个文件（原始文件名 + 内容 SHA-256）已归过就跳过——重复点「归案」
    不该在案件日志里堆出十条一样的记录。
    """
    paths = _collect_files(Path(directory))
    return ingest_files(
        case_id=case_id,
        paths=paths,
        actor=actor,
        content=content,
        material_type_name=material_type_name,
        category=category,
        side=side,
        parse_now=parse_now,
        backend=backend,
    )


def ingest_files(
    *,
    case_id: int,
    paths: list[Path],
    actor: Any = None,
    content: str = DEFAULT_LOG_CONTENT,
    material_type_name: str = "客户提供材料",
    category: str = CaseMaterialCategory.PARTY,
    side: str = CaseMaterialSide.OUR,
    parse_now: bool = True,
    backend: str = "auto",
) -> list[CaseMaterial]:
    """按文件列表归案（与 `ingest_directory` 同一套口径）。"""
    if not paths:
        return []
    log = _ensure_log(case_id=case_id, actor=actor, content=content)
    created: list[CaseMaterial] = []
    for path in paths:
        material = _ingest_one(
            log=log,
            case_id=case_id,
            path=Path(path),
            material_type_name=material_type_name,
            category=category,
            side=side,
            parse_now=parse_now,
            backend=backend,
        )
        if material is not None:
            created.append(material)
    logger.info("材料归案完成: case=%s 文件=%d 新登记=%d", case_id, len(paths), len(created))
    return created


def _collect_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise ValueError(f"目录不存在: {directory}")
    files = [
        path
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES and path.name not in _SKIP_NAMES
    ]
    return files


def _ensure_log(*, case_id: int, actor: Any, content: str) -> CaseLog:
    """一次归案一条日志。`actor` 缺省取案件承办律师——CaseLog.actor 是 PROTECT，不能为空。"""
    resolved_actor = actor or _fallback_actor(case_id=case_id)
    return CaseLog.objects.create(case_id=case_id, content=content, actor=resolved_actor)


def _fallback_actor(*, case_id: int) -> Any:
    """承办律师 → 全所第一个律师：`CaseLog.actor` 是 PROTECT，不能为空。

    承办关系挂在 `Case.assignments` 上（一个案件可有多名律师），取第一条即「主承办」；
    早期案件没有指派记录时退回全所第一个律师——归案日志的署名不该成为阻塞点。
    """
    from apps.organization.models import Lawyer

    assignment = Lawyer.objects.filter(case_assignments__case_id=case_id).order_by("id").first()
    lawyer = assignment or Lawyer.objects.order_by("id").first()
    if lawyer is None:
        raise ValueError("库里没有任何律师可用于登记案件日志（CaseLog.actor 不能为空）")
    return lawyer


def _ingest_one(
    *,
    log: CaseLog,
    case_id: int,
    path: Path,
    material_type_name: str,
    category: str,
    side: str,
    parse_now: bool,
    backend: str,
) -> CaseMaterial | None:
    if not path.exists():
        logger.warning("归案跳过（文件不存在）: %s", path)
        return None
    size = path.stat().st_size
    if size == 0:
        logger.warning("归案跳过（空文件）: %s", path)
        return None
    if size > MAX_FILE_BYTES:
        logger.warning("归案跳过（超过 %d MiB）: %s", MAX_FILE_BYTES // 1024 // 1024, path)
        return None

    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if CaseMaterial.objects.filter(case_id=case_id, source_file_hash=digest).exists():
        logger.info("归案跳过（同内容已登记）: %s", path.name)
        return None

    attachment = CaseLogAttachment.objects.create(
        log=log,
        file=SimpleUploadedFile(name=path.name, content=raw),
        original_filename=path.name,
    )
    task = _parse(path=path, parse_now=parse_now, backend=backend)
    with transaction.atomic():
        material = CaseMaterial.objects.create(
            case_id=case_id,
            type_name=material_type_name,
            category=category,
            side=side,
            source_attachment=attachment,
            source_file_hash=digest,
            parsing_task=task,
        )
    return material


def _parse(*, path: Path, parse_now: bool, backend: str) -> Any:
    """就地解析并落一条完成任务；失败返回 None（材料照样登记）。"""
    if not parse_now:
        return None
    from apps.document_parsing.exceptions.parsing_exceptions import DocumentParsingError
    from apps.document_parsing.models import DocumentParsingTask
    from apps.document_parsing.services.document_parser import DocumentParserService

    try:
        parsed = DocumentParserService(backend=backend).parse_document(
            file_path=str(path), file_type=path.suffix.lower().lstrip(".")
        )
    except (DocumentParsingError, OSError, RuntimeError, TimeoutError, ValueError):
        # 收窄到「解析侧故障」：后端报错、文件读不了、模型侧抛 RuntimeError、参数/格式不对。
        # 程序性错误（NameError/ImportError 等）照常抛——否则真 bug 会被这条兜底永久掩盖。
        logger.warning("材料解析失败，已登记但无正文: %s", path.name, exc_info=True)
        return None
    text = (parsed.text or "").strip()
    markdown = (parsed.markdown or "").strip()
    if not text and not markdown:
        logger.warning("材料解析结果为空: %s", path.name)
        return None
    return DocumentParsingTask.objects.create(
        file_name=path.name,
        file_path=str(path),
        file_size=path.stat().st_size,
        status=DocumentParsingTask.Status.COMPLETED,
        backend_used=str(parsed.parse_method or backend),
        text=text,
        markdown=markdown,
        metadata=parsed.metadata or {},
        completed_at=timezone.now(),
    )


__all__ = ["DEFAULT_LOG_CONTENT", "MAX_FILE_BYTES", "SUPPORTED_SUFFIXES", "ingest_directory", "ingest_files"]
