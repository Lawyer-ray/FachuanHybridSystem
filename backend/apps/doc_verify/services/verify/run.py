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

## 什么时候升级到 tier 1（以及 OCR 结果怎么落地）

提取完入站件才知道到底要不要花钱：`resolve_tier()` 只看「入站件有没有文本层」
与「律师勾没勾核对」，落库的 tier 是它算出来的**实际值**，不是入参。

OCR 结果有两处落点，顺序是硬的：覆盖度先写 `coverage["ocr"]`（花了多少钱、
补了几页），灰项再补进 findings，然后才 `derive_state()`。反过来的话，
「预算用尽」「引擎不可用」会被推导成 `verified_clean`——一句系统没有证据
支持的绿灯，比不核更糟。
"""

from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import replace
from typing import Any, get_args

from django.db import IntegrityError, transaction

from apps.core.exceptions import ValidationException
from apps.doc_verify.domain.contracts import AssertionKind, Baseline, Finding, Inbound, Report, Severity, Tier
from apps.doc_verify.domain.normalize import split_pages
from apps.doc_verify.domain.states import derive_state
from apps.doc_verify.models import VerificationRun, VerifyState
from apps.doc_verify.services.verify import deps, notify

logger = logging.getLogger(__name__)
from apps.doc_verify.services.verify.tier import TIER_OCR, resolve_tier

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
    tier: int | None = None,
) -> Any:
    """对一份回传件跑一次核对，返回 `VerificationRun`（已存在则返回既有行）。

    只写 `VerificationRun`：不写裁决，也不回写 artifact 的任何字段。
    落库的 `tier` 是 `resolve_tier()` 算出的实际值（扫描件 + 勾了核对会自动升到
    OCR 层），不是入参原样透传。
    """
    if tier is not None and tier not in TIERS:
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

    # 显式层级且不高于既有结论 → 不用取字就能判，保持原来的零成本重放。
    # （取字要解析整本 PDF，几十毫秒到几百毫秒；OCR 才是贵的那一段，见下。）
    existing = VerificationRun.objects.filter(run_key=run_key).first()
    if existing is not None and tier is not None and tier <= existing.tier:
        return existing

    # 未指定层级时要先取字：**层数取决于入站件有没有文本层**，不是入参说了算。
    # 少了这一步，「先跑免费层看看、可疑再花钱核」这条路永远回不到 OCR 层——
    # 同一份字节只能永远停在灰的「未发现差异」。
    inbound = deps.extract_document(data, file_name)
    actual_tier = resolve_tier(
        requested=tier,
        verify_required=bool(artifact.verify_required),
        inbound_text=inbound.text,
    )

    if existing is not None and not _upgradable(existing=existing, actual_tier=actual_tier):
        return existing

    inbound, fill = _inbound_with_ocr(data=data, inbound=inbound, tier=actual_tier, artifact=artifact)
    report = _report_for(artifact=artifact, inbound=inbound, tier=actual_tier)
    _record_ocr(report=report, fill=fill)
    state = derive_state(report)
    if existing is not None:
        upgraded = _upgrade_run(
            existing=existing,
            inbound=inbound,
            report=report,
            state=state,
            file_name=file_name,
            source_message_id=source_message_id,
            tier=actual_tier,
        )
        # 写库成功之后才通知：待办说的是「这一行结论」，不是「打算核」。
        # 失败由 notify 内部吞掉（核对结论不能被待办搞挂）；这条路径手里没有操作人。
        notify.notify_pending_decision(run=upgraded, actor=None)
        return upgraded
    created = _create_run(
        artifact=artifact,
        run_key=run_key,
        inbound=inbound,
        report=report,
        state=state,
        file_name=file_name,
        source_message_id=source_message_id,
        tier=actual_tier,
    )
    notify.notify_pending_decision(run=created, actor=None)
    return created


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
    """幂等键：同一基线 + 同一入站字节 = 同一次核对。

    刻意**不含 tier**：同一份回传件不会因为「这次多花了 OCR 的钱」变成另一件事。
    把 tier 掺进键里，第一次跑 tier 0、再跑 tier 1 就会落两行同一事实的记录。
    """
    material = f"{artifact_id}:{inbound_sha256}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:64]


def _inbound_with_ocr(*, data: bytes, inbound: Any, tier: int, artifact: Any = None) -> tuple[Any, Any | None]:
    """tier ≥ 1 且有页没有文本层时用 OCR 补字，返回（实际参与比对的入站件, OCR 结果）。

    补字判据是**逐页**的：整篇没字（扫描件）、中间夹着扫描页、末尾几页没字
    （提取层只拼有字的页）都要补。`pages_failed` 那几页随后由比对引擎报
    `PAGE_NO_TEXT`，落成 gray。

    `hint_pages` 由**页指纹**给出：基线渲染页 vs 回传件页面距超阈值的页先 OCR。
    它只调顺序、不做筛选——每一页最终都要核对（律师的原话：不可能只核前 10 页）。
    先出可疑页的结论，是为了让律师不用等整本 OCR 完才看到第一条红线。
    """
    if tier < TIER_OCR or not _has_page_without_text(inbound):
        return inbound, None
    fill = deps.fill_text_with_ocr(
        data=data,
        inbound=inbound,
        hint_pages=_hint_pages(artifact=artifact, inbound=inbound),
    )
    # `Inbound` 是 frozen：替换出一个新对象，「提取结果」与「比对输入」才是两份事实。
    return replace(inbound, text=fill.text), fill


def _hint_pages(*, artifact: Any, inbound: Any) -> tuple[int, ...]:
    """指纹指出「哪几页看着不一样」，作为 OCR 的**排序提示**（1-based）。

    只在两侧都有指纹、且页数一致时才给提示：页数不一致时页码本来就不对齐，
    按页码猜会把「第 3 页可疑」指到错误的内容上，比不给提示更糟。

    阈值沿用副本识别的 `SAME_PAGE_MAX_DISTANCE`——它衡量的是「像不像同一页」，
    正好是这里要的语义；拿它当「改没改」的判据才是不对的（单字改动它看不出来）。
    """
    if artifact is None:
        return ()
    baseline_signatures = _page_signatures(artifact.page_signatures)
    inbound_signatures = tuple(inbound.page_signatures or ())
    if not baseline_signatures or not inbound_signatures:
        return ()
    if len(baseline_signatures) != len(inbound_signatures):
        return ()
    from apps.pdf_splitting.services.split.page_fingerprint import SAME_PAGE_MAX_DISTANCE, signature_distance

    hints: list[int] = []
    for index, (left, right) in enumerate(zip(baseline_signatures, inbound_signatures), start=1):
        if signature_distance(left, right) > SAME_PAGE_MAX_DISTANCE:
            hints.append(index)
    return tuple(hints)


def _has_page_without_text(inbound: Any) -> bool:
    """入站件是否有页没有文本层。"""
    pages = split_pages(inbound.text)
    if not pages:
        return True
    if len(pages) < int(inbound.page_count):
        return True
    return any(not page.strip() for page in pages)


def _record_ocr(*, report: Report, fill: Any | None) -> None:
    """把 OCR 结果写进覆盖度，并补上**先于状态推导**的灰项。

    没跑 OCR 就不写 `coverage["ocr"]`：那张覆盖度表里没有「花了多少钱补字」
    这个事实，写一个全零的壳只会让人以为跑了。
    """
    if fill is None:
        return
    report.coverage["ocr"] = {
        "pages_attempted": fill.pages_attempted,
        "pages_filled": fill.pages_filled,
        "pages_failed": fill.pages_failed,
        "budget_exhausted": bool(fill.budget_exhausted),
        "engine": fill.engine,
    }
    report.findings.extend(_ocr_findings(fill))


def _ocr_findings(fill: Any) -> list[Finding]:
    """OCR 的两种「没核完」：预算用尽、引擎不在。都是 gray——不给绿灯。"""
    findings: list[Finding] = []
    if fill.budget_exhausted:
        findings.append(
            Finding(
                kind=AssertionKind.COVERAGE,
                code="OCR_BUDGET_EXHAUSTED",
                title="OCR 预算用尽，仍有页未核对",
                severity=Severity.GRAY,
            )
        )
    if fill.engine == "unavailable":
        findings.append(
            Finding(
                kind=AssertionKind.COVERAGE,
                code="OCR_UNAVAILABLE",
                title="OCR 引擎不可用，无法核对正文",
                severity=Severity.GRAY,
            )
        )
    return findings


def _report_for(*, artifact: Any, inbound: Any, tier: int) -> Report:
    """跑比对。

    **不在这里自己短路「字节相同」**：比对引擎的第一步就是 sha 相同直接返回
    `bytes_identical` 覆盖度，短路两次等于给同一个事实两处实现——其中一处迟早
    会少写一个 coverage 键，于是「原样回传」被报成「未发现差异」。
    """
    return deps.compare_documents(_baseline_from_artifact(artifact), inbound, tier=tier)


def _upgradable(*, existing: Any, actual_tier: int) -> bool:
    """这份既有运行能不能被更高一层重算。

    两条都要满足：
    1. 这次算出来的层**严格更高**（降级没意义：证据更弱的结论不能盖掉更强的）；
    2. 还没有任何裁决——`list_unverified` 是靠「有 accept/reject 就排除」来收敛清单的，
       所以裁决后再改结论，不仅和那份裁决矛盾，还会让新的红线**从待裁决清单里消失**。
       已有裁决就原样返回，并在日志里干一句：要重核就得先作废裁决/换基线。
    """
    if actual_tier <= existing.tier:
        return False
    if existing.decisions.exists():
        logger.warning(
            "回传件已有裁决，不自动升级重核: run=%s 既有 tier=%s 请求 tier=%s",
            existing.pk,
            existing.tier,
            actual_tier,
        )
        return False
    return True


def _upgrade_run(
    *,
    existing: Any,
    inbound: Any,
    report: Report,
    state: str,
    file_name: str,
    source_message_id: int | None,
    tier: int,
) -> Any:
    """把一次运行从免费层**原地升级**到 OCR 层，不新开一行。

    为什么不把 tier 并进 `run_key`：那样同一份字节会有两行，待裁决清单里同一件事
    出现两次——这正是幂等键要消灭的东西。为什么可以原地改：`VerificationRun` 记的是
    「这份件现在的结论」，留痕靠 append-only 的裁决；升级后的结论证据严格强于旧的，
    留着旧的那条只会让律师看见一个已经过时的「未发现差异」。
    """
    existing.tier = tier
    existing.state = state
    existing.inbound_file_name = inbound.file_name or file_name
    existing.page_count = inbound.page_count
    existing.findings = report.findings_dicts()
    existing.coverage = dict(report.coverage or {})
    if source_message_id is not None:
        existing.source_message_id = source_message_id
    existing.save(
        update_fields=[
            "tier",
            "state",
            "inbound_file_name",
            "page_count",
            "findings",
            "coverage",
            "source_message_id",
        ]
    )
    logger.info("回传件核对原地升级: run=%s tier=%s state=%s", existing.pk, tier, state)
    return existing


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
