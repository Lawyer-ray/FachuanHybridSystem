"""合同自动分析导入的编排层。

串起「临时落盘 → 文本提取 → LLM 抽取 → 归一化 → 库内关联匹配 → 返回草稿」。

关于临时文件：按用户要求，待识别合同**不入库**（不建 ``FinalizedMaterial``），
只落在 ``MEDIA_ROOT/tmp/contract_intake/`` 下，由既有定时任务
``apps.core.tasking.cleanup_tasks.cleanup_temp_files`` 每小时按 mtime 清理
（该任务扫的就是 ``MEDIA_ROOT/tmp`` 递归树，无需新增调度）。

这也是为什么本模块不写任何业务表：用户复核后才点「保存」，
届时走既有 ``ContractAdmin.save_model``，临时文件不参与。

错误文案卫生约定（硬性，勿破）：
    ``ContractIntakeError`` 的消息会**原样回显到前端**（admin 里 ``str(exc)``
    直接进 JsonResponse）。所以链路上任何一环都**不得**把底层异常文本拼进文案：
    ``OSError`` 带绝对路径、``pymupdf`` / ``python-docx`` 带解析器内部结构、
    LLM SDK 带 HTTP 请求体与鉴权头片段。一律给固定、可操作的中文提示，
    底层详情用 ``raise ... from exc`` 保留在异常链里，由上层
    ``logger.exception`` 记录。破这条会触发 CodeQL py/stack-trace-exposure，
    也是真实的向外部泄露实现细节。
"""

from __future__ import annotations

import logging
import re
import secrets
from pathlib import Path
from typing import IO, Any

from django.conf import settings
from django.utils import timezone

from apps.contracts.services.contract.intake.document_snapshot import (
    SUPPORTED_SUFFIXES,
    DocumentSnapshotError,
    build_snapshot,
    detect_suffix,
)
from apps.contracts.services.contract.intake.extract_schema import ContractExtraction
from apps.contracts.services.contract.intake.extract_service import ContractExtractionError, extract_contract
from apps.contracts.services.contract.intake.normalize import ContractDraft, normalize_extraction

logger = logging.getLogger(__name__)

#: 临时目录（相对 MEDIA_ROOT）。落在 ``tmp/`` 下才能被既有清理任务覆盖。
_TEMP_SUBDIR = Path("tmp") / "contract_intake"
#: 单份合同上传上限：合同 PDF 通常几 MB，50MB 足够且能挡住误传的大文件
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
#: 识别调用的墙钟预算（秒）。kimi 处理长合同实测 30-90 秒，300 秒留足余量，
#: 又不至于让浏览器/网关等到超时。
EXTRACT_BUDGET_SECONDS = 300


class ContractIntakeError(Exception):
    """导入流程的可预期错误（消息可直接展示给用户）。"""


def _sanitize_stem(filename: str) -> str:
    """从原始文件名取安全的展示用主名（去路径、去危险字符）。"""
    stem = Path(str(filename or "")).stem
    stem = re.sub(r"[^\w\u4e00-\u9fff\-_. ]+", "_", stem).strip() or "contract"
    return stem[:80]


def _temp_dir() -> Path:
    path = Path(settings.MEDIA_ROOT) / _TEMP_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_temp_upload(uploaded_file: IO[bytes], *, filename: str) -> Path:
    """把上传文件落到临时目录，返回路径。

    文件名加随机后缀避免并发同名覆盖；原始文件名单独记录用于展示，
    因为落盘名里的随机串对用户无意义。
    """
    # detect_suffix 抛的是 DocumentSnapshotError（文档层异常），但调用方只捕获
    # ContractIntakeError——不在这里转一道，用户传错文件会看到 500 而不是可读提示。
    try:
        suffix = detect_suffix(filename)
    except DocumentSnapshotError as exc:
        raise ContractIntakeError(str(exc)) from exc
    stem = _sanitize_stem(filename)
    token = secrets.token_hex(8)
    target = _temp_dir() / f"{stem}-{token}{suffix}"
    try:
        with target.open("wb") as handle:
            for chunk in iter(lambda: uploaded_file.read(1024 * 1024), b""):
                handle.write(chunk)
    except OSError as exc:
        # OSError 的文本带绝对路径、磁盘/权限细节，不能拼进用户可见文案
        # （CodeQL py/stack-trace-exposure）：详情只进日志，对外给可操作提示
        logger.exception("合同临时文件写入失败")
        raise ContractIntakeError("文件保存失败（磁盘或权限问题），请重试或联系管理员") from exc
    return target


def build_client_lookup() -> dict[str, tuple[int, str]]:
    """构建 ``{匹配键: (id, 展示名)}``，供当事人在库内自动关联。

    键包含「精确名称」与「证照号」两种：证照号更可靠（名称常有简称/错字），
    归一化层会优先用证照号命中。
    """
    from apps.client.models import Client

    lookup: dict[str, tuple[int, str]] = {}
    for client_id, name, id_number in Client.objects.values_list("id", "name", "id_number").iterator():
        label = str(name or "")
        if not label:
            continue
        lookup.setdefault(label.strip(), (client_id, label))
        if id_number:
            lookup.setdefault(str(id_number).strip(), (client_id, label))
    return lookup


def build_lawyer_lookup() -> dict[str, tuple[int, str]]:
    """构建 ``{归一化姓名: (id, 展示名)}``。

    律师姓名可按 ``real_name`` 或 ``username`` 命中；同名只保留第一个，
    让用户在前端下拉里自行确认（不自动创建律师，避免脏数据）。
    """
    from apps.contracts.services.contract.intake.normalize import normalize_lawyer_name_key
    from apps.organization.models import Lawyer

    lookup: dict[str, tuple[int, str]] = {}
    for lawyer_id, real_name, username in Lawyer.objects.values_list("id", "real_name", "username").iterator():
        label = str(real_name or username or "").strip()
        if not label:
            continue
        for candidate in (real_name, username):
            key = normalize_lawyer_name_key(candidate or "")
            if key:
                lookup.setdefault(key, (lawyer_id, label))
    return lookup


def resolve_our_law_firm(*, user: Any) -> tuple[str, int | None]:
    """返回当前登录律师所在律所的 ``(名称, id)``。

    多律所共同承办的合同里，「本同金额是 ¥1 万还是 ¥2 万」完全取决于我方是哪家律所——
    这是**关键上下文**，必须从登录身份取，不能靠模型猜。

    取不到时返回 ``("", None)``，后续金额归属会退回「合同总额 + 提示人工确认」。
    """
    law_firm = getattr(user, "law_firm", None)
    if law_firm is None:
        return "", None
    return str(getattr(law_firm, "name", "") or "").strip(), getattr(law_firm, "id", None)


def analyze_contract(
    *,
    path: Path,
    filename: str,
    model_id: str = "",
    user: Any = None,
) -> dict[str, Any]:
    """分析一份已落盘合同，返回可回填表单的草稿字典。

    Args:
        path: 临时文件路径。
        filename: 原始文件名（决定解析器与展示）。
        model_id: 用户选定的模型；空串走平台默认模型。
        user: 当前登录律师。用于确定「我方律所」与默认承办律师——
            这两项对金额归属和律师指派是决定性的，不能交给模型猜。

    Returns:
        ``{"draft": {...}, "document": {...}, "model": "..."}``

    Raises:
        ContractIntakeError: 格式不支持、无文本、LLM 不可用或抽取失败。
    """
    try:
        snapshot = build_snapshot(path=path, filename=filename)
    except DocumentSnapshotError as exc:
        raise ContractIntakeError(str(exc)) from exc

    our_firm_name, our_firm_id = resolve_our_law_firm(user=user)

    try:
        extraction: ContractExtraction = extract_contract(
            snapshot=snapshot,
            model_id=model_id,
            our_law_firm=our_firm_name,
        )
    except ContractExtractionError as exc:
        raise ContractIntakeError(str(exc)) from exc

    draft: ContractDraft = normalize_extraction(
        extraction,
        client_lookup=build_client_lookup(),
        lawyer_lookup=build_lawyer_lookup(),
        our_law_firm=our_firm_name,
        current_lawyer_id=getattr(user, "pk", None),
    )

    # 文档层告警与模型层提示合并，前端统一展示
    warnings = list(snapshot.warnings) + list(draft.warnings)
    if draft.notes:
        warnings.append(f"模型提示：{draft.notes}")

    return {
        "draft": draft.as_dict(),
        "document": {
            "filename": snapshot.filename,
            "paragraph_count": snapshot.paragraph_count,
            "table_count": snapshot.table_count,
            "char_count": snapshot.char_count,
            "truncated": snapshot.truncated,
            "analyzed_at": timezone.localtime().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "warnings": list(dict.fromkeys(warnings)),
        "model": model_id or "(平台默认)",
    }


def intake_options() -> dict[str, Any]:
    """新建页初始化所需的元数据：可选模型、支持的文件类型、大小上限。"""
    from apps.contracts.services.contract.intake.extract_service import available_models, default_model_of

    models = available_models()
    accepted = ",".join(sorted(SUPPORTED_SUFFIXES))
    return {
        "models": models,
        "default_model": default_model_of(),
        "accept": accepted,
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "llm_ready": bool(models),
    }
