"""日期候选服务

职责链：提取合并（LLM key_events + 正则候选）→ 落库为候选行 →
律师人工确认后写入重要日期提醒 → 撤销。

设计要点（评审定稿）：
- 幂等由候选行状态机承担：事务内 ``select_for_update`` 锁行，已 confirmed
  的行直接返回原 reminder_id；**不走** ``upsert_case_log_reminder_internal``
  （它按 case_log+source 定位只取一条，多日期会互相覆盖）。
- 确认写提醒按优先级取关联锚点：``case_log_id`` → ``case_id`` → 独立提醒
  （Reminder 的 contract/case/case_log 最多绑一个）。任务已绑定案件但日志尚未
  落库时挂案件本身，避免产出三字段全空的孤立提醒；两者都无才是独立提醒
  （快捕获场景不强制选案，metadata 带 task 溯源）。
- 存量自动写入的旧提醒无 metadata.source：确认前按
  ``(case_log_id, due_at)`` 查重复用，避免同一时间出现双提醒。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException
from apps.reminders.models import ReminderType

from .data_classes import DocumentType
from .date_candidate_policy import (
    FLAG_ANCHOR_FOREIGN_LLM,
    FLAG_ANCHOR_UNKNOWN,
    AnchorDocument,
    AnchorKind,
    CandidateDecision,
    anchor_note_for,
    classify_document_role,
    confidence_for,
    decide_candidate,
    extract_period_length_verdict,
    party_role_verdict,
    period_length_anchor,
    period_length_event_type,
)

# 拆分后的原地 re-export：实现已下沉到兄弟模块，但**路径不变**——调用方与单测
# 仍按 ``date_candidate_service.<名字>`` import，公开签名与行为一致。
#   - 纯规则层（常量/正则表、期间与相对期限推算、``DateCandidateDraft``、
#     ``parse_candidate_datetime``）→ ``date_candidate_rules``
#   - 落库与序列化层（``persist_candidates`` / ``reconcile_source_candidates`` /
#     ``list_candidates`` / ``refresh_task_confirmation_status`` /
#     ``_get_task_for_update``）→ ``date_candidate_repository``
# 私有正则/表常量（``_PERIOD_RANGE_RE`` 等）只留在规则层内部使用，不再从本模块透出。
from .date_candidate_repository import (
    _get_task_for_update,
    list_candidates,
    persist_candidates,
    reconcile_source_candidates,
    refresh_task_confirmation_status,
)
from .date_candidate_rules import (
    DEFAULT_TYPE_BY_DOCUMENT_TYPE,
    EFFECTIVE_FIRST_NOTE,
    FAR_FUTURE_DAYS,
    MAX_CANDIDATES,
    REMINDER_TYPE_PRIORITY,
    STALE_DAYS,
    DateCandidateDraft,
    _apply_period_rules,
    _apply_relative_deadline_rules,
    _dedupe_same_context,
    _find_issue_date,
    _has_explicit_year,
    _is_effective_first_derived,
    _is_judgment_document,
    _is_party_payment_obligation,
    _normalize_aware,
    _parse_cn_number,
    _RegexCandidateExtractor,
    _reminder_type_label,
    _self_title_keywords,
    _suppress,
    _verdict_from_draft,
    parse_candidate_datetime,
)

logger = logging.getLogger("apps.document_recognition")

REMINDER_SOURCE = "document_recognition"


def build_date_candidates(
    text: str,
    analysis: Any | None,
    document_type: DocumentType,
    *,
    regex_extractor: Any | None = None,
    received_at: datetime | None = None,
    sibling_documents: Sequence[str] | None = None,
    our_party_roles: Sequence[str] | None = None,
    suppressed_out: list[dict[str, Any]] | None = None,
) -> list[DateCandidateDraft]:
    """合并 LLM key_events 与正则候选为去重后的候选列表。

    去重键 = (日期时间, 提醒类型)：同值 LLM 优先（source 升级为 merged、
    置信度取 max）；同日不同类型都保留（开庭日与举证截止同日是真实场景）。

    Args:
        received_at: 文书送达/收到时间（法院短信的 ``CourtSMS.received_at``）。
            传入时作为「送达之日起 N 日」类期限的起算锚点（见
            ``_apply_relative_deadline_rules``）；None 则回落到落款日。
        sibling_documents: 同一条短信/同批次的其他文书显示名。用来把
            「应自收到《缴费通知书》之日起七日内」判成"期限归属另一份文书"（丢弃）。
        our_party_roles: 我方在该案的诉讼地位（``CaseParty.legal_status``，只取
            ``Client.is_our_client=True`` 的当事人）。用于「举证期限只在我方是
            被告/被申请人/被上诉人/第三人时才需要跟」这条业务口径；None 表示
            拿不到地位 → 保留候选但标 ``party_role_unknown``、不默认勾。
        suppressed_out: 出参：被闸门丢弃的候选会追加到这里，调用方落库到
            ``task.suppressed_candidates`` 留痕（律师问「为什么没提醒」时能答）。
            用出参而不是改返回值，是为了不打断既有的 list 返回约定与全部现有单测。
    """
    extractor = regex_extractor or _RegexCandidateExtractor()
    default_type = DEFAULT_TYPE_BY_DOCUMENT_TYPE.get(document_type, "other")
    siblings = tuple(sibling_documents or ())
    # 本文书自己的类型名（如「裁定书」）：复议期句子里写的是「收到裁定书之日起五日内」，
    # 指的是本份裁定而非别份，必须让锚点判定知道这件事。
    self_titles = _self_title_keywords(text)
    # 文书角色：这份文书到底承不承载本案期限（内容判据，不看文件名）
    role, role_reason = classify_document_role(text=text)
    logger.info("文书角色判定: %s | %s", role.value, role_reason)

    drafts: dict[tuple[datetime, str], DateCandidateDraft] = {}

    # 1. LLM 事件
    key_events = list(getattr(analysis, "key_events", None) or [])
    for event in key_events:
        parsed = parse_candidate_datetime(str(getattr(event, "datetime", "") or ""))
        if parsed is None:
            logger.warning("LLM 日期事件解析失败，跳过: %s", getattr(event, "datetime", None))
            continue
        event_type = getattr(event, "event_type", "other") or "other"
        if event_type not in ReminderType.values:
            event_type = "other"
        context = str(getattr(event, "context", "") or "")[:255]
        # 无年份日期不采纳：原文若只写「3月26日」，LLM 会按文档里出现的年份自行补全，
        # 猜错一年就让律师跟进错期限（2026-11-14 实测执行裁定书「3月26日冻结一年」
        # 被补成 2026-03-26，算出的到期日提前了整整一年）。宁可少一条，
        # 也不给一个看上去确定、实际可能差一年的假日期。
        if not _has_explicit_year(parsed, context, text):
            logger.warning(
                "跳过无年份的 LLM 日期事件（不猜年份）: %s | context=%s",
                getattr(event, "datetime", None),
                context[:40],
            )
            continue
        # LLM 自报的起算锚归属（anchor_hint）：它说锚在别处（尚未产生的裁判文书/
        # 另一份具名文书）时，本条就是不可算的——直接丢弃并留痕，不信它的日期。
        anchor_hint = str(getattr(event, "anchor_hint", "self") or "self")
        # LLM 说「锚在别份文书」时不直接采信它的日期，但也不直接丢：
        # 模型标错一次的代价是漏掉真期限（如把「本份执行通知书」标成 other_document）。
        # 保留草稿 + 打 flag + 不默认勾，把「到底是不是别份文书的期限」交回确定性层
        # 与律师本人判断（详见 date_candidate_policy 的设计原则 P1/P5）。
        llm_foreign_anchor = anchor_hint in ("future_document", "other_document")
        if llm_foreign_anchor:
            logger.info("LLM 判定锚点在别份文书（%s），保留为待核对候选: %s", anchor_hint, parsed.date())
        drafts[(parsed, event_type)] = DateCandidateDraft(
            due_at=parsed,
            reminder_type=event_type,
            context_text=context,
            source="llm",
            confidence=float(getattr(event, "confidence", 0.7) or 0.7),
            derivation="llm_absolute",
            anchor_document="self",
            anchor_kind=AnchorKind.EFFECTIVE_DATE.value if anchor_hint == "effective" else "",
            review_flags=(FLAG_ANCHOR_FOREIGN_LLM,) if llm_foreign_anchor else (),
        )

    # 2. 正则候选（透出全部，含上下文与类型推断）
    def _merge_regex_candidate(candidate: dict[str, Any]) -> None:
        """把一条正则候选并入草稿表（同日期同类型去重、LLM 优先）。"""
        parsed = candidate["datetime"]
        reminder_type = candidate.get("reminder_type") or default_type
        key = (parsed, reminder_type)
        regex_confidence = round(min(float(candidate.get("context_score", 0)), 100) / 100 * 0.85, 2)
        existing = drafts.get(key)
        if existing is None:
            drafts[key] = DateCandidateDraft(
                due_at=parsed,
                reminder_type=reminder_type,
                context_text=str(candidate.get("context_text", ""))[:255],
                source="regex",
                confidence=regex_confidence,
                derivation="rule_absolute",
                anchor_document="self",
            )
        else:
            existing.source = "merged"
            existing.confidence = max(existing.confidence, regex_confidence)
            if not existing.context_text:
                existing.context_text = str(candidate.get("context_text", ""))[:255]

    for candidate in extractor.extract_datetime_candidates(text):
        _merge_regex_candidate(candidate)

    # 2.5 纯日期（无时刻）兜底：DATETIME_PATTERNS 全部要求时刻，
    #     「本案举证期限至 2027-01-10 止」这类只有 LLM 能抓；LLM 熔断时就全空。
    #     门槛由 mixin 内的"上下文必须命中期限词"保证，不会成片抓叙事日期。
    for candidate in extractor.extract_date_only_candidates(text):
        _merge_regex_candidate(candidate)

    # 3. 期间结构后处理：起始日剔除、到期日算术校正、相对期限推算、同上下文去重
    drafts_list = _apply_period_rules(text, list(drafts.values()))
    for draft in drafts_list:
        if not draft.derivation:
            draft.derivation = "rule_period"
        if not draft.anchor_document:
            draft.anchor_document = "self"
    # 3.2 期间长度（「举证期限为十五日」）：与「…之日起 N 日内」是两种写法，
    #     前者是法院给本案**指定**的期限长度，必须能算；但法定下限/多档程序不算。
    period_verdict = extract_period_length_verdict(text)
    period_context = period_length_anchor(text) or period_verdict.matched_text
    period_type = period_length_event_type(text)
    anchor_day = received_at.date() if received_at else None
    if anchor_day is None:
        issue = _find_issue_date(text)
        anchor_day = issue.date() if issue else None
    # 起算点可能早于本次送达：真实模板常写「自当事人收到**起诉状副本及举证通知书**之日起计算」。
    # 起诉状副本与前序文书可能不同批送达，拿本次短信收到日当锚会把截止日算**晚**
    # （律师以为还有时间，实际已过）。这种情况保留候选但不默认勾，逼人工核对实际收到日。
    anchor_mentions_complaint = bool(period_context) and (
        "起诉状" in period_context and not any(kw in period_context for kw in ("本通知", "本举证通知书"))
    )
    if period_verdict.stated_days is not None and not period_verdict.reason and anchor_day is not None:
        period_due = datetime.combine(anchor_day, datetime.min.time()) + timedelta(days=period_verdict.stated_days)
        drafts_list.append(
            DateCandidateDraft(
                due_at=period_due,
                reminder_type=period_type,
                context_text=(period_context or period_verdict.matched_text)[:255],
                source="regex",
                confidence=0.9,
                anchor_kind=AnchorKind.SERVICE_OF_SELF.value if received_at else AnchorKind.ISSUE_DATE_OF_SELF.value,
                anchor_at=anchor_day,
                anchor_document=AnchorDocument.SELF.value,
                derivation="rule_period",
                review_flags=(FLAG_ANCHOR_UNKNOWN,) if anchor_mentions_complaint else (),
                anchor_note=anchor_note_for(
                    kind=AnchorKind.SERVICE_OF_SELF if received_at else AnchorKind.ISSUE_DATE_OF_SELF,
                    anchor_at=anchor_day,
                    delivery_date=anchor_day,
                    days=period_verdict.stated_days,
                ),
            )
        )
        logger.info("期间长度推算候选: 届满=%s (%s + %d天)", period_due.date(), anchor_day, period_verdict.stated_days)
    elif period_verdict.reason:
        # 算不出来的要留痕：多档程序 / 法定下限 / 无起算点，都可能在律师追问时被问到
        _suppress(
            suppressed_out,
            deadline=datetime.combine(anchor_day or timezone.localdate(), datetime.min.time()),
            event_type=period_type,
            context=period_context or period_verdict.matched_text,
            verdict=None,
            reason=period_verdict.reason,
        )

    drafts_list = _apply_relative_deadline_rules(
        text,
        drafts_list,
        delivery_date=received_at,
        role=role,
        sibling_documents=siblings,
        self_titles=self_titles,
        suppressed=suppressed_out,
    )

    # 4. 陈旧候选降置信（改判文书可能含历史日期，折叠而非丢弃）
    today = timezone.localdate()
    for draft in drafts_list:
        if (today - draft.due_at.date()).days > STALE_DAYS:
            draft.confidence = min(draft.confidence, 0.3)

    # 4.4 剔除纯历史事实日期：律师要记的是**尚未到来的期限**。
    #
    # 判决书/裁定书正文密集出现已发生的日期：立案日、签约日、对账日、落款日……
    # 它们不是“关键日期”，只是叙事时间线，放进日历没有意义而且会混淆真正的期限。
    # 因此：**已过去且类型为 other** 的候选直接丢弃（不返回、不落库）。
    # 保留例外：
    #   - 未来日期（哪怕类型是 other，也可能是尚未归类的期限）；
    #   - 己过期但类型明确的候选（如上诉期已过、保全到期已过）——
    #     律师需要知道“这个已经过了”，审计/追责时用得上，不能默默隐藏。
    # 保留两个兜底：
    #   a) 已过期 + other → 叙事时间线，丢弃；
    #   b) 超过 FAR_FUTURE_DAYS 的 far-future 日期（>10 年）→ 降置信到 0.3 且标 other，
    #      这类多是别处的长期约定（房贷 30 年到期日、土地租期）被当成本文书期限。
    #      实测（2026-11-14 全量扫描）：一份银行贷款合同给出 2051-04-25。
    #      不直接删——如果律师真的要跟进，行还在，只是不默认勾选。
    kept: list[DateCandidateDraft] = []
    for draft in drafts_list:
        past = draft.due_at.date() < today
        if past and draft.reminder_type == "other":
            continue
        if (draft.due_at.date() - today).days > FAR_FUTURE_DAYS:
            draft.confidence = min(draft.confidence, 0.3)
        kept.append(draft)
    drafts_list = kept

    # 4.55 判决书 / 调解书：只保留救济期限（上诉期、复议期），剔除判项给付义务
    # 与正文引述的合同条款付款期（业务口径：那是当事人自己的事，与律师日历无关）。
    if _is_judgment_document(text):
        before = len(drafts_list)
        drafts_list = [d for d in drafts_list if not _is_party_payment_obligation(d, text)]
        if len(drafts_list) != before:
            logger.info(
                "判决书/调解书剔除当事人给付义务期限: %d → %d 条",
                before,
                len(drafts_list),
            )

    # 4.6 标注「生效之日起算」的履行期限（不丢弃，见 _EFFECTIVE_FIRST_RE 注释）
    #
    # 旧实现把置信度压到**恰好 0.5**，而前端阈值是「>= 0.5 就默认勾」——
    # 「降一档、默认不勾」的意图反向失效（2026-11-24 审计发现）。现在改成
    # 只打锚点标记，由下面的 decide_candidate 统一下调置信度并挂 flag，
    # 默认勾选只看 flags，不再有压线边界。
    for draft in drafts_list:
        if draft.anchor_kind == AnchorKind.EFFECTIVE_DATE.value or _is_effective_first_derived(draft, text):
            draft.anchor_kind = AnchorKind.EFFECTIVE_DATE.value
            draft.anchor_note = EFFECTIVE_FIRST_NOTE

    # 4.7 逐条裁决：该留还是该丢、带哪些复核标记、能不能默认勾。
    # 这里是「provenance 策略」的唯一出口，前端不再按裸分数自己判断。
    decided: list[DateCandidateDraft] = []
    for draft in drafts_list:
        verdict = _verdict_from_draft(draft)
        confidence = confidence_for(
            derivation=draft.derivation or "llm_absolute",
            anchor=verdict,
            role=role,
            raw=draft.confidence,
        )
        party_role_ok, party_role_reason = party_role_verdict(our_party_roles, draft.context_text)
        decision = decide_candidate(
            derivation=draft.derivation or "llm_absolute",
            anchor=verdict,
            role=role,
            confidence=confidence,
            due_at=draft.due_at,
            today=today,
            party_role_ok=party_role_ok,
        )
        if party_role_ok is False:
            decision = CandidateDecision(
                keep=False,
                flags=decision.flags,
                confidence=decision.confidence,
                default_checked=False,
                reason=party_role_reason,
            )
        if not decision.keep:
            logger.info(
                "丢弃候选: %s %s | %s",
                draft.due_at.date(),
                draft.reminder_type,
                decision.reason,
            )
            _suppress(
                suppressed_out,
                deadline=draft.due_at,
                event_type=draft.reminder_type,
                context=draft.context_text,
                verdict=verdict,
                reason=decision.reason,
            )
            continue
        merged_flags: list[str] = list(draft.review_flags)
        for flag in decision.flags:
            if flag not in merged_flags:
                merged_flags.append(flag)
        draft.review_flags = tuple(merged_flags)
        # 取 min 而不是覆盖：前置的陈旧降权（STALE_DAYS → 0.3）与远期降权不能被重算抹平
        draft.confidence = min(draft.confidence, decision.confidence)
        draft.default_checked = decision.default_checked
        # 草稿上预先打的 flag（如"起算点可能早于本次送达"）同样要收回默认勾选
        if merged_flags:
            draft.default_checked = False
        if not draft.anchor_document:
            draft.anchor_document = AnchorDocument.SELF.value
        decided.append(draft)
    drafts_list = decided

    # 5. 名额分配：**未过期候选优先占 MAX_CANDIDATES 名额**。
    # 判决书正文里密布已发生的事实日期（立案/签约/对账/落款），它们不是“提醒”，
    # 却会把真正的期限（如末页的上诉期）挤出名额——实测 7 页判决书里
    # 6 条历史日期与 2 条真期限同为候选，旧逻辑靠类型优先级勉强不死，
    # 一旦历史日期被 LLM 归成 hearing/payment_deadline 就会顶掉真期限。
    # 过期候选仍然保留（折叠到最后，律师仍可看到并手动勾选），只是不占前排。
    ordered = sorted(
        drafts_list,
        key=lambda d: (
            0 if d.due_at.date() >= today else 1,  # 未过期在前
            REMINDER_TYPE_PRIORITY.get(d.reminder_type, 99),
            -d.confidence,
            d.due_at,
        ),
    )
    return _dedupe_same_context(ordered)[:MAX_CANDIDATES]


def _resolve_reminder_service() -> Any:
    from apps.reminders.services.wiring import get_reminder_service

    return get_reminder_service()


def _build_reminder_content(reminder_type: str, context_text: str) -> str:
    label = _reminder_type_label(reminder_type)
    snippet = (context_text or "").strip()[:60]
    return f"{label}：{snippet}" if snippet else label


@transaction.atomic
def confirm_candidates(task_id: int, items: list[dict[str, Any]], user: Any | None = None) -> list[dict[str, Any]]:
    """批量确认/忽略日期候选，逐项返回结果。

    每项: {candidate_id, action: confirm|skip, due_at?, reminder_type?}。
    幂等：已 confirmed 的候选直接返回原 reminder_id。
    非归属人非管理员对任务不可见 → NotFoundError（404）。
    """
    from apps.document_recognition.models import DateCandidateStatus, DocumentRecognitionStatus

    task = _get_task_for_update(task_id, user)
    if task.status != DocumentRecognitionStatus.SUCCESS:
        raise ValidationException(
            message="任务尚未识别完成，不能确认日期",
            code="TASK_NOT_READY",
            errors={},
        )

    user_id = getattr(user, "id", None) if user else None
    reminder_service = _resolve_reminder_service()
    now = timezone.now()
    results: list[dict[str, Any]] = []

    candidate_ids = [item["candidate_id"] for item in items]
    locked_rows = {row.id: row for row in task.date_candidates.select_for_update().filter(id__in=candidate_ids)}

    for item in items:
        results.append(
            _confirm_single_item(
                task=task,
                item=item,
                row=locked_rows.get(item["candidate_id"]),
                reminder_service=reminder_service,
                user_id=user_id,
                user=user,
                now=now,
            )
        )

    refresh_task_confirmation_status(task)
    return results


def _confirm_single_item(
    *,
    task: Any,
    item: dict[str, Any],
    row: Any | None,
    reminder_service: Any,
    user_id: int | None,
    user: Any | None = None,
    now: datetime,
) -> dict[str, Any]:
    from apps.document_recognition.models import DateCandidateStatus

    candidate_id = item["candidate_id"]
    action = item.get("action", "confirm")

    if row is None:
        return {
            "candidate_id": candidate_id,
            "status": "error",
            "reminder_id": None,
            "message": "候选不存在",
            "error_code": "CANDIDATE_NOT_FOUND",
        }

    if action == "skip":
        if row.status == DateCandidateStatus.CONFIRMED:
            return {
                "candidate_id": candidate_id,
                "status": "confirmed",
                "reminder_id": row.reminder_id,
                "message": "候选已确认过提醒，忽略无效",
                "error_code": None,
            }
        row.status = DateCandidateStatus.SKIPPED
        row.save(update_fields=["status", "updated_at"])
        return {
            "candidate_id": candidate_id,
            "status": "skipped",
            "reminder_id": None,
            "message": "已忽略",
            "error_code": None,
        }

    # action == confirm
    if row.status == DateCandidateStatus.CONFIRMED and row.reminder_id:
        return {
            "candidate_id": candidate_id,
            "status": "confirmed",
            "reminder_id": row.reminder_id,
            "message": "已确认过，幂等返回",
            "error_code": None,
        }

    due_at_raw = item.get("due_at") or row.due_at.isoformat()
    parsed = parse_candidate_datetime(str(due_at_raw)) if isinstance(due_at_raw, str) else due_at_raw
    if parsed is None:
        return {
            "candidate_id": candidate_id,
            "status": "error",
            "reminder_id": None,
            "message": "时间格式不正确",
            "error_code": "INVALID_TIME_FORMAT",
        }
    aware_due_at = _normalize_aware(parsed)

    reminder_type = item.get("reminder_type") or row.reminder_type
    if reminder_type not in ReminderType.values:
        return {
            "candidate_id": candidate_id,
            "status": "error",
            "reminder_id": None,
            "message": f"不支持的提醒类型: {reminder_type}",
            "error_code": "INVALID_REMINDER_TYPE",
        }

    message = "已写入提醒"
    reminder = _find_existing_reminder(reminder_service, task, aware_due_at)
    if reminder is not None:
        message = "复用了同时间点的既有提醒，未重复创建"
    else:
        reminder = reminder_service.create_reminder(
            **_reminder_binding_kwargs(task),
            reminder_type=reminder_type,
            content=_build_reminder_content(reminder_type, row.context_text),
            due_at=aware_due_at,
            metadata={
                "source": REMINDER_SOURCE,
                "source_id": f"task:{task.id}:candidate:{row.id}",
                "task_id": task.id,
            },
            # 安全审计 M-1：记录创建人（该提醒关联案件日志，写权限由案件 ACL
            # 决定；created_by 仅为可追溯性补全，不改变权限口径）
            created_by=user,
        )
        # 确认过的重要日期默认列入案件「重要时间」视图（服务层无该参数，落实例后补写）
        reminder.include_in_important_time = True
        reminder.save(update_fields=["include_in_important_time"])

    row.due_at = aware_due_at
    row.reminder_type = reminder_type
    row.status = DateCandidateStatus.CONFIRMED
    row.reminder_id = reminder.id
    row.confirmed_by_id = user_id
    row.confirmed_at = now
    row.save(
        update_fields=[
            "due_at",
            "reminder_type",
            "status",
            "reminder_id",
            "confirmed_by_id",
            "confirmed_at",
            "updated_at",
        ]
    )

    logger.info(
        "日期候选已确认: task_id=%s, candidate_id=%s, reminder_id=%s, case_log_id=%s, case_id=%s, standalone=%s",
        task.id,
        candidate_id,
        reminder.id,
        task.case_log_id,
        task.case_id,
        task.case_log_id is None and task.case_id is None,
    )
    return {
        "candidate_id": candidate_id,
        "status": "confirmed",
        "reminder_id": reminder.id,
        "message": message,
        "error_code": None,
    }


def _reminder_binding_kwargs(task: Any) -> dict[str, Any]:
    """确认写提醒时的关联锚点，按优先级回落（Reminder 三者最多绑一个，故只能选一个）。

    只认 case_log_id 会让「案件已绑定、日志尚未落库」的任务（识别完成到日志创建
    之间确认日期就是这种时序）产出三个关联字段全空的孤立提醒，日历上显示
    「未关联案件」且无补救入口。任务已绑定案件时退一步挂案件本身是正确归属。
    两者都无才是真正的独立提醒（快捕获场景，不强制选案）。
    """
    if task.case_log_id is not None:
        return {"case_log_id": task.case_log_id}
    if task.case_id is not None:
        return {"case_id": task.case_id}
    return {"case_log_id": None}


def _find_existing_reminder(reminder_service: Any, task: Any, aware_due_at: datetime) -> Any | None:
    """按 (case_log_id, due_at) 查重复用（含无 source 的旧自动提醒）；独立提醒无查重域。

    查重域刻意不扩到 case_id（属语义变更，会改变「同一时间点是否复用既有提醒」）：
    该域回收的是「存量自动写入的旧提醒」（按案件日志时间比对），而 case_id 域里
    混着任务自己确认过的及其它模块建的整案级提醒。放宽后确认日期可能复用一条
    同刻但来源/语义不同的提醒，候选行会指向不是本功能创建的 reminder（撤销时被
    NOT_REVOKABLE 拦住，用户无从清理）；且 case_id 级提醒覆盖整案多个时间点，
    同刻命中概率远高于 case_log。宁可多一条挂在案件上的提醒，也不改语义。
    """
    if task.case_log_id is None:
        return None
    existing = reminder_service.list_reminders(case_log_id=task.case_log_id)
    for reminder in existing:
        if reminder.due_at == aware_due_at:
            return reminder
    return None


@transaction.atomic
def revoke_confirmation(task_id: int, candidate_id: int, user: Any | None = None) -> dict[str, Any]:
    """撤销确认：删除本功能创建的提醒，候选行回到待确认。

    非归属人非管理员对任务不可见 → NotFoundError（404）。
    """
    from apps.document_recognition.models import DateCandidateStatus, DocumentRecognitionDateCandidate

    task = _get_task_for_update(task_id, user)
    try:
        row = task.date_candidates.select_for_update().get(id=candidate_id)
    except DocumentRecognitionDateCandidate.DoesNotExist:
        raise NotFoundError(message="候选不存在", code="CANDIDATE_NOT_FOUND", errors={}) from None

    if row.status != DateCandidateStatus.CONFIRMED:
        raise ValidationException(message="候选未确认，无需撤销", code="NOT_CONFIRMED", errors={})

    if row.reminder_id:
        reminder_service = _resolve_reminder_service()
        reminder = reminder_service.get_reminder(row.reminder_id)
        metadata = reminder.metadata if isinstance(reminder.metadata, dict) else {}
        if metadata.get("source") != REMINDER_SOURCE:
            raise ValidationException(
                message="该提醒不是文书识别创建的，不能在此撤销",
                code="NOT_REVOKABLE",
                errors={},
            )
        reminder_service.delete_reminder(reminder.id)

    row.status = DateCandidateStatus.PENDING
    row.reminder_id = None
    row.confirmed_by_id = None
    row.confirmed_at = None
    row.save(update_fields=["status", "reminder_id", "confirmed_by_id", "confirmed_at", "updated_at"])
    refresh_task_confirmation_status(task)

    logger.info("日期候选已撤销: task_id=%s, candidate_id=%s", task_id, candidate_id)
    return {
        "candidate_id": candidate_id,
        "status": "pending",
        "reminder_id": None,
        "message": "已撤销并删除提醒",
        "error_code": None,
    }
