"""入站核对的编排：一次回传件只落一行运行记录。

## 为什么幂等键是（基线, 入站字节）的哈希，而不是时间

同一份回传件会被多条链路看见：邮件附件、回传链接、归案时手工上传。
三条链路各跑一次比对，就会得到三行「同一事实」的记录——律师在待裁决
清单里看到同一份件出现三次，这份清单就没人信了。所以 `run_key` 只认
`artifact.id + 入站字节 SHA-256`：先到的落库，后到的复用同一行。

## 为什么这一层不写裁决、不改基线

裁决是律师的意思表示（append-only 留痕），基线是出站那一刻冻结的证据。
编排层只负责把「这一次比对看到了什么」写清楚；它替任何一方做主张，
出事时那份记录就不再是证据。

## 状态从哪来

`derive_state()` 是唯一入口：状态由发现项（以及「字节是否相同」这个硬事实）
推导，不接受调用方拍板。前端按状态上色，状态一错，报告说的就是一句
没有证据的话。
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any, get_args

from django.db import IntegrityError, transaction

from apps.core.exceptions import ValidationException
from apps.doc_verify.domain.contracts import Baseline, Inbound, Report, Tier
from apps.doc_verify.domain.states import derive_state
from apps.doc_verify.models import VerificationRun, VerifyState
from apps.doc_verify.services.verify import deps

#: 核对层级只认 domain 契约里的 `Tier`（0 免费层 / 1 OCR / 2 重核），
#: 不在这里另写一份取值表——两份口径迟早会漂。
TIERS: tuple[int, ...] = get_args(Tier)

#: 与 `VerificationRun.inbound_file_name` 的列宽一致。超长在 PostgreSQL 上是
#: DataError（500），在这里拦成 400：文件名是调用方给的参数，不是服务端故障。
FILE_NAME_MAX_LENGTH = 255


def decode_inbound_payload(file_base64: str) -> bytes:
    """回传件 base64（前端带 `data:` 前缀也收）→ 字节。

    放在服务层而不是 API 层：四层规范禁止 API 层写 try/except，而解码必须把
    非法输入拦成 `ValidationException`（否则是 500）。`validate=True` 是刻意的——
    宽容解码会把「传了一半的 base64」解成一段能跑比对、但内容错的字节，报告
    随后会说「有改动」，而事实是文件没传完整。
    """
    text = (file_base64 or "").strip()
    if not text:
        raise ValidationException(message="回传件内容为空", errors={"file_base64": "不能为空"})
    if text.startswith("data:"):
        _, _, text = text.partition(",")
    try:
        data = base64.b64decode(text, validate=True)
    except ValueError:
        raise ValidationException(
            message="file_base64 不是合法的 base64",
            errors={"file_base64": "解码失败"},
        ) from None
    if not data:
        raise ValidationException(message="回传件内容为空", errors={"file_base64": "解码后为空"})
    return data


def verify_inbound(
    *,
    artifact: Any,
    data: bytes,
    file_name: str = "",
    source_message_id: int | None = None,
    tier: int = 0,
) -> Any:
    """对一份回传件跑一次核对，返回 `VerificationRun`（已存在则返回既有行）。

    只写 `VerificationRun`：不写裁决，也不回写 artifact 的任何字段。
    """
    if tier not in TIERS:
        raise ValidationException(message=f"核对层级不合法：{tier}", errors={"tier": list(TIERS)})
    if not data:
        raise ValidationException(message="回传件内容为空", errors={"data": "不能为空"})
    if len(file_name or "") > FILE_NAME_MAX_LENGTH:
        raise ValidationException(
            message="回传文件名过长",
            errors={"file_name": f"最多 {FILE_NAME_MAX_LENGTH} 个字符"},
        )

    inbound_sha256 = hashlib.sha256(data).hexdigest()
    run_key = _run_key(artifact_id=artifact.id, inbound_sha256=inbound_sha256)
    existing = VerificationRun.objects.filter(run_key=run_key).first()
    if existing is not None:
        return existing

    inbound = deps.extract_document(data, file_name)
    report = _report_for(artifact=artifact, inbound=inbound, tier=tier)
    state = derive_state(report)
    return _create_run(
        artifact=artifact,
        run_key=run_key,
        inbound=inbound,
        report=report,
        state=state,
        file_name=file_name,
        source_message_id=source_message_id,
        tier=tier,
    )


def verify_existing_bytes(*, artifact: Any, tier: int = 0) -> Any:
    """按基线**已存**的快照自检比对引擎，返回 `Report`。

    为什么至少要有 tier=1：免费层只比页数/页指纹，而自检的两侧读的是同一份
    JSONField——它们恒等，「通过」这个结论里没有任何信息量。

    为什么不写 `VerificationRun`：自检没有「客户回传」这个事实。硬写一行会让
    核对历史里出现一条没有入站件的记录，而且它的 run_key 会与「客户原样回传」
    的真实运行撞车（同一个 sha256）——两条完全不同的事挤进同一行。
    """
    if tier not in (1, 2):
        raise ValidationException(message="基线自检至少需要 tier=1", errors={"tier": tier})
    return deps.compare_documents(
        _baseline_from_artifact(artifact),
        _inbound_from_artifact(artifact),
        tier=tier,
    )


def _run_key(*, artifact_id: int, inbound_sha256: str) -> str:
    """幂等键：同一基线 + 同一入站字节 = 同一次核对。"""
    material = f"{artifact_id}:{inbound_sha256}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:64]


def _report_for(*, artifact: Any, inbound: Any, tier: int) -> Report:
    """跑比对。

    **不在这里自己短路「字节相同」**：比对引擎的第一步就是 sha 相同直接返回
    `bytes_identical` 覆盖度，短路两次等于给同一个事实两处实现——其中一处迟早
    会少写一个 coverage 键，于是「原样回传」被报成「未发现差异」。
    """
    return deps.compare_documents(_baseline_from_artifact(artifact), inbound, tier=tier)


def _create_run(
    *,
    artifact: Any,
    run_key: str,
    inbound: Any,
    report: Report,
    state: str,
    file_name: str,
    source_message_id: int | None,
    tier: int,
) -> Any:
    """落一行运行记录；并发下唯一约束是最终判据。"""
    try:
        # savepoint：IntegrityError 会中止当前事务，不套 atomic 的话外层事务（含测试事务）一起废掉
        with transaction.atomic():
            return VerificationRun.objects.create(
                artifact=artifact,
                run_key=run_key,
                state=state,
                tier=tier,
                inbound_file_name=inbound.file_name or file_name,
                inbound_sha256=inbound.sha256,
                page_count=inbound.page_count,
                findings=report.findings_dicts(),
                coverage=dict(report.coverage or {}),
                source_message_id=source_message_id,
            )
    except IntegrityError:
        # 另一条链路在 filter 与 create 之间落了同一 run_key。幂等的定义就是「先写成功的那行胜出」。
        return VerificationRun.objects.get(run_key=run_key)


def _baseline_from_artifact(artifact: Any) -> Baseline:
    """把 artifact 行上冻结的字段还原成契约形状（不做容差、不做补全）。"""
    return Baseline(
        doc_type=artifact.doc_type,
        version=artifact.version or "",
        sha256=artifact.file_sha256,
        page_count=artifact.page_count,
        page_signatures=_page_signatures(artifact.page_signatures),
        text=artifact.text_layer or "",
        masks=tuple(dict(mask) for mask in (artifact.masks or ())),
    )


def _inbound_from_artifact(artifact: Any) -> Inbound:
    """自检用的「入站件」：直接取基线自己存下来的快照。"""
    return Inbound(
        sha256=artifact.file_sha256,
        page_count=artifact.page_count,
        page_signatures=_page_signatures(artifact.page_signatures),
        text=artifact.text_layer or "",
        file_name=artifact.file_name or "",
    )


def _page_signatures(raw: Any) -> tuple[tuple[float, ...], ...]:
    """JSONField 存的是 list[list[float]]，契约要 tuple[tuple[float, ...], ...]。

    只做形状转换、不做异常吞掉：形状不对是数据坏了，不该在这里被悄悄抹平成空。
    """
    return tuple(tuple(float(value) for value in row) for row in (raw or ()))
