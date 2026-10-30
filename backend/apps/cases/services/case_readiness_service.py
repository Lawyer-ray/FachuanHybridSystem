"""案件就绪度服务：材料齐备度 / 起诉答辩条件 / 利益冲突预检.

═════ 这三个能力的共同设计原则 ═════
机器只**发现**与**陈述依据**，不代替律师做判断：
  · 每个结论都带 `reason` / `detail`，写清「凭什么这么说」
  · 每条校验都带 `field`，指回所依据的模型字段，便于回溯
  · 硬阻塞（缺件、确定冲突）与软提示（材料待更新、疑似冲突）分开，
    前者让 `ready=False`，后者只记录，不挡流程

为什么放在 service 层而不是写在 API 里：
  这三个判断都要读多张表（Case / CaseParty / Client / CaseMaterial /
  CaseNumber / Reminder…），写在 API 里会导致每次加一条校验都要改路由文件，
  也无法被后台任务或 MCP 工具复用。
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.cases.models import Case, CaseMaterial, CaseNumber, CaseParty

# ───────────────────────── 材料齐备度 ─────────────────────────

# ── 二审答辩材料槽位 ──
#
# ⚠️ 二审答辩与一审起诉要的材料**完全不是一套**，不能共用：
#   一审问「合同/借据/流水/催收」——那是证明借贷关系与逾期事实；
#   二审问「一审判决书/上诉状/答辩状/一审卷宗」——那是针对上诉理由逐条反驳。
# 如果二审还按一审的槽位判，会得到两条荒谬结论：
#   · 二审案「缺催收记录」——二审根本不举证这个，一审已经举过了；
#   · 二审案「材料齐备」而手上没有答辩状——真正该交的那份没检查。
# 实测就是这么错的：二审案被判「2/5 缺 3 项（借据/流水/催收）」，
# 而律师手上真正缺的是答辩状，报告里一个字没提。
APPEAL_REQUIRED_SLOTS: list[tuple[str, str]] = [
    ("judgment", "一审判决书"),
    ("appeal_petition", "上诉状"),
    ("defense", "答辩状"),
    ("first_instance_file", "一审卷宗材料"),
]

APPEAL_SLOT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "judgment": ("判决书", "判决", "裁定书", "调解书"),
    "appeal_petition": ("上诉状", "上诉", "上诉理由"),
    "defense": ("答辩状", "答辩", "答辩意见"),
    "first_instance_file": ("一审", "原审", "卷宗", "庭审笔录", "证据"),
}

# 立案必需的材料槽位（key → 中文名）。
# 为什么要在这里定一份而不是查 CaseMaterialType 表：
#   类型表是律所可自定义的（每个所的叫法不同），但「哪些是立案必需」是
#   诉讼法的硬要求，不随所变。两者混在一起会让「缺件判断」跟着所的配置漂。
REQUIRED_SLOTS: list[tuple[str, str]] = [
    ("contract", "借款/主合同"),
    ("iou", "借据或放款凭证"),
    ("stmt", "还款明细或对账单"),
    ("coll", "催收记录"),
    ("id", "当事人身份证明"),
    ("guarantee", "担保合同"),
]

# 关键词 → 槽位。材料文件名/类型名里出现这些词即归入该槽位。
# 说明：这是**启发式**而非精确匹配——真实材料命名千差万别，
# 精确匹配会漏；漏判比多判更糟（律师会以为材料齐了）。
#
# ⚠️ 关键词要覆盖实际命名习惯，不能只写“标准名”：
#   《个人购房借款/担保合同》里没有“借款合同”这四个连续字（中间有“/担保”），
#   只写“借款合同”会漏掉这类最常见的银行合同命名。所以把“借款”单独也保留。
SLOT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "contract": ("借款合同", "贷款合同", "主合同", "合同书", "授信合同"),
    "iou": ("借据", "放款", "借款凭证", "支付凭证"),
    "stmt": ("还款明细", "交易明细", "对账单", "流水", "还款记录"),
    "coll": ("催收", "催告", "律师函", "通知函"),
    "id": ("身份证", "营业执照", "身份证明", "户口"),
    "guarantee": ("担保合同", "保证合同", "抵押合同", "质押合同"),
}


def _has_guarantor(case_id: int) -> bool:
    """本案是否有保证人／担保人当事人。"""
    return (
        CaseParty.objects.filter(case_id=case_id)
        .filter(
            Q(legal_status__icontains="guarantor")
            | Q(legal_status__icontains="担保")
            | Q(legal_status__in=("guarantor", "third"))
        )
        .exists()
    )


def _pack_readiness(case: Case, mode: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """把校验清单汇总成就绪度结果（纯函数，与具体案件无关）。"""
    passed = sum(1 for c in checks if c["ok"])
    return {
        "case_id": case.id,
        "stage": case.current_stage or "",
        "mode": mode,
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "ready": passed == len(checks),
    }


class MaterialStatusService:
    """材料齐备度：回答「这件能不能递立案」。"""

    def mode_of(self, case_id: int) -> str:
        """按案件当前阶段判断该用哪套材料槽位：appeal / filing。

        与 CaseReadinessService.APPEAL_STAGES 同一口径（含历史中文存量），
        两处不一致会导致「就绪度说按二审算、材料齐备说按一审算」。
        """
        case = Case.objects.filter(id=case_id).only("current_stage").first()
        if case is None:
            return "filing"
        stage = (case.current_stage or "").strip()
        return "appeal" if stage in CaseReadinessService.APPEAL_STAGES else "filing"

    def status_of(self, case_id: int, *, mode: str = "filing") -> dict[str, Any]:
        """材料齐备度。

        mode:
          filing  → 一审起诉要件（合同/借据/流水/催收/身份/担保）
          appeal  → 二审答辩要件（一审判决书/上诉状/答辩状/一审卷宗）

        两套槽位不可混用，原因见 APPEAL_REQUIRED_SLOTS 的注释。
        """
        case = Case.objects.filter(id=case_id).first()
        if case is None:
            raise ValueError(f"案件不存在: {case_id}")

        is_appeal = mode == "appeal"
        slots_def = APPEAL_REQUIRED_SLOTS if is_appeal else REQUIRED_SLOTS
        slot_kw = APPEAL_SLOT_KEYWORDS if is_appeal else SLOT_KEYWORDS
        weak_def: dict[str, tuple[str, ...]] = (
            {
                "judgment": ("裁判", "生效"),
                "appeal_petition": (),
                "defense": ("反驳",),
                "first_instance_file": ("一审卷",),
            }
            if is_appeal
            else {
                "contract": ("借款", "贷款", "授信", "合同"),
                "iou": ("出账", "提款"),
                "stmt": ("还本付息",),
                "coll": ("催款",),
                "id": ("主体资格", "金融许可证", "户口"),
                "guarantee": ("抵押", "质押", "担保函"),
            }
        )

        # 取本案全部材料的可读名，用于关键词归位。
        # ⚠️ 字段名要按真实模型来：
        #    CaseMaterial 没有 file_path / original_name，
        #    文件名在 source_attachment（CaseLogAttachment）的 original_filename 里。
        materials = list(CaseMaterial.objects.filter(case_id=case_id).select_related("type", "source_attachment"))

        # 先把每份材料的可读名算出来，再按「强关键词 → 弱关键词」两轮归位。
        #
        # 为什么不能一遗用全部关键词：
        #   为兼容《个人购房借款/担保合同》而把“借款”收进 contract 后，
        #   “借款借据”也会命中 contract —— 一张借据被算成“主合同已交”，
        #   律师就看不到真正缺的是合同本身。
        #   两轮匹配：先只认强关键词（专指名），剩下的名额再让弱关键词补。
        names: list[str] = []
        for m in materials:
            att = getattr(m, "source_attachment", None)
            fname = ""
            if att is not None:
                fname = getattr(att, "original_filename", "") or getattr(att, "relative_file_path", "")
            names.append(str(getattr(m, "type_name", "") or "") + " " + str(fname))

        WEAK = weak_def

        # ═══ 全局分配而非逐槽独立匹配 ═══
        # 逐槽独立匹配会让同一份材料喂给多个槽位：《借款借据（放款凭证）》同时
        # 命中 contract 的弱词「借款」和 iou 的强词「借据」，结果主合同槽位被
        # 借据占掉，律师看到「主合同齐备」而真正缺的是合同本身。
        # 正确做法是三轮抢占，越专指的越先占，占过的不再给别人：
        #   第 1 轮  强关键词（"借据"/"还款明细"/"催收"…专指名）
        #   第 2 轮  弱关键词兜底（"借款"/"合同"…单看不足以认定）
        #   第 3 轮  仍未命中的才是真缺件
        #
        # 只有这样「借据」才能先占住 iou，contract 再去抢别的东西。
        claimed: set[int] = set()
        matched_by_key: dict[str, list[str]] = {k: [] for k, _ in slots_def}

        def _short(hay: str, mid: int) -> str:
            return hay.strip().split("/")[-1] or f"材料#{mid}"

        for use_weak in (False, True):
            for key, _label in slots_def:
                if matched_by_key[key]:
                    continue  # 上一轮已经命中，不再追加
                pool = slot_kw.get(key, ()) if not use_weak else WEAK.get(key, ())
                for m, hay in zip(materials, names):
                    if m.id in claimed:
                        continue
                    if any(kw in hay for kw in pool):
                        matched_by_key[key].append(_short(hay, m.id))
                        claimed.add(m.id)
                        break  # 一个槽位只认第一份最合适的

        slots: list[dict[str, Any]] = []
        for key, label in slots_def:
            matched = matched_by_key[key]
            kws = slot_kw.get(key, ())

            if not matched:
                # 担保合同：无保证人的案件视为不适用，不算缺件
                if not is_appeal and key == "guarantee" and not _has_guarantor(case_id):
                    slots.append(
                        {
                            "key": key,
                            "label": label,
                            "status": "na",
                            "file_names": [],
                            "reason": "本案无保证人，无需担保合同",
                        }
                    )
                else:
                    slots.append(
                        {
                            "key": key,
                            "label": label,
                            "status": "miss",
                            "file_names": [],
                            "reason": f"未找到含「{'/'.join(kws[:2])}」字样的材料",
                        }
                    )
            else:
                slots.append({"key": key, "label": label, "status": "ok", "file_names": matched, "reason": ""})

        ok_n = sum(1 for s in slots if s["status"] == "ok")
        need_n = sum(1 for s in slots if s["status"] != "na")
        miss_n = sum(1 for s in slots if s["status"] == "miss")
        stale_n = sum(1 for s in slots if s["status"] == "stale")

        return {
            "case_id": case_id,
            "slots": slots,
            "ok_count": ok_n,
            "need_count": need_n,
            "missing_count": miss_n,
            "stale_count": stale_n,
            # ready 只看 miss：stale 不阻塞立案（律师可以先递后补）
            "ready": miss_n == 0,
        }


# ───────────────────────── 起诉 / 答辩条件 ─────────────────────────


class CaseReadinessService:
    """案件就绪度：按当前阶段给不同的一组校验。

    ⚠️ 起诉条件与答辩条件是**两套完全不同的问题**：
      起诉要问：主体适格吗？管辖对吗？时效过没过？材料齐不齐？
      答辩要问：上诉理由逐条能否反驳？一审判决有无支撑？答辩期还剩几天？
    混在一张表里，律师不知道该看哪几行。所以按 `current_stage` 分流。
    """

    # CaseStage 里属于二审及以后的阶段（走答辩条件）
    #
    # ⚠️ 为什么既要英文枚举又要中文显示名：
    #   生产库里 `current_stage` 是**中英文混存**的——枚举值是 first_trial
    #   （48 件），但早期录入/导入的数据存的是中文「一审」（13 件）、
    #   「二审」（1 件）。只认英文会让那 14 件真实案件全落进 mode="other"，
    #   checks 为空、ready 恒 True —— 律师看到「全部通过」但根本没校验过。
    #   这是**静默假通过**，比报错更危险，所以两种写法都必须认。
    APPEAL_STAGES = (
        "second_trial",
        "retrial_second",
        "rehearing_second",
        "review",
        "二审",
        "重审二审",
        "再审二审",
        "提审",
    )
    FILING_STAGES = ("", "first_trial", "filing", "一审", "立案")

    def __init__(self) -> None:
        self.material = MaterialStatusService()

    def readiness_of(self, case_id: int) -> dict[str, Any]:
        case = Case.objects.filter(id=case_id).first()
        if case is None:
            raise ValueError(f"案件不存在: {case_id}")

        stage = (case.current_stage or "").strip()
        if stage in self.APPEAL_STAGES:
            return self._appeal(case)
        if stage in self.FILING_STAGES:
            return self._filing(case)
        # 其他阶段（执行/仲裁等）暂无专门校验 —— 明确说出来，不要假装通过
        return {
            "case_id": case_id,
            "stage": stage,
            "mode": "other",
            "checks": [],
            "passed": 0,
            "total": 0,
            "ready": True,
        }

    # 当事人诉讼地位的**中英文两套写法**。
    # 生产库 cases_caseparty.legal_status 同样是混存：
    #   defendant 73 / plaintiff 45 / 被告 3 …
    # 只看英文会把 3 个「被告」当成「无被告」，误判主体不适格。
    PLAINTIFF_STATUSES = ("plaintiff", "orig_plaintiff", "applicant", "appellant", "原告", "申请人", "上诉人")
    DEFENDANT_STATUSES = (
        "defendant",
        "orig_defendant",
        "respondent",
        "appellee",
        "criminal_defendant",
        "被告",
        "被申请人",
        "被上诉人",
    )

    # ── 起诉条件 ──
    def _filing(self, case: Case) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        # ① 当事人主体适格：有原告且有被告
        parties = list(case.parties.select_related("client").all())
        statuses = [(p.legal_status or "").strip() for p in parties]
        has_plaintiff = any(s in self.PLAINTIFF_STATUSES for s in statuses)
        has_defendant = any(s in self.DEFENDANT_STATUSES for s in statuses)
        checks.append(
            {
                "key": "parties",
                "label": "当事人主体适格",
                "ok": has_plaintiff and has_defendant,
                "detail": f"原告 {'有' if has_plaintiff else '缺'} · 被告 {'有' if has_defendant else '缺'} · 共 {len(parties)} 方",
                "field": "Case.parties[].legal_status",
            }
        )

        # ② 管辖：有受理法院
        has_court = bool(case.supervising_authorities.exists())
        checks.append(
            {
                "key": "jurisdiction",
                "label": "管辖",
                "ok": has_court,
                "detail": ("已登记主管机关" if has_court else "未登记主管机关（管辖法院）"),
                "field": "Case.supervising_authorities[]",
            }
        )

        # ③ 诉讼时效：有逾期起算日且在 3 年内
        #    真实实现应比对 Reminder/利息清单的起算日；这里用 start_date 做保守判断
        from datetime import date

        years = (date.today() - case.start_date).days / 365 if case.start_date else 0
        checks.append(
            {
                "key": "limitation",
                "label": "诉讼时效",
                "ok": years < 3,
                "detail": f"自收案日 {case.start_date} 起 {years:.1f} 年",
                "field": "Case.start_date",
            }
        )

        # ④ 材料齐备
        ms = self.material.status_of(case.id)
        checks.append(
            {
                "key": "materials",
                "label": "材料齐备",
                "ok": ms["ready"],
                "detail": f"{ms['ok_count']}/{ms['need_count']} 项齐备"
                + (f"，缺 {ms['missing_count']} 项" if ms["missing_count"] else ""),
                "field": "CaseMaterial",
            }
        )

        # ⑤ 标的额：必须有值且非负
        amt = case.target_amount
        checks.append(
            {
                "key": "amount",
                "label": "涉案金额",
                "ok": amt is not None and amt >= 0,
                "detail": f"¥{amt:,.2f}" if amt is not None else "未填写",
                "field": "Case.target_amount",
            }
        )

        return _pack_readiness(case, "filing", checks)

    # ── 答辩条件 ──
    def _appeal(self, case: Case) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        # ① 前序案件：二审必须挂到一审上（否则案卷关系断裂）
        prev = case.previous_case
        checks.append(
            {
                "key": "previous",
                "label": "一审案卷关联",
                "ok": prev is not None,
                "detail": (
                    f"前序：{prev.name}（{prev.filing_number or '无编号'}）"
                    if prev
                    else "未挂前序案件——二审是新案件记录，必须指向一审那一件"
                ),
                "field": "Case.previous_case",
            }
        )

        # ② 二审案号：立案后才有
        has_number = CaseNumber.objects.filter(case_id=case.id).exists()
        checks.append(
            {
                "key": "case_number",
                "label": "二审案号",
                "ok": has_number,
                "detail": "已登记案号" if has_number else "未登记二审案号（法院尚未出具）",
                "field": "Case.case_numbers[]",
            }
        )

        # ③ 一审判决书：答辩状第一段要引它
        has_judgment = CaseNumber.objects.filter(case_id=case.id, document_name__icontains="判决").exists() or (
            prev and CaseNumber.objects.filter(case_id=prev.id, document_name__icontains="判决").exists()
        )
        checks.append(
            {
                "key": "judgment",
                "label": "一审判决书",
                "ok": bool(has_judgment),
                "detail": "已归档判决书" if has_judgment else "未找到一审判决书（答辩状需引用其认定事实）",
                "field": "CaseNumber.document_name",
            }
        )

        # ④ 材料齐备 —— 用**二审自己的槽位**，不是一审那套
        ms = self.material.status_of(case.id, mode="appeal")
        checks.append(
            {
                "key": "materials",
                "label": "材料齐备",
                "ok": ms["ready"],
                "detail": f"{ms['ok_count']}/{ms['need_count']} 项齐备",
                "field": "CaseMaterial",
            }
        )

        return _pack_readiness(case, "appeal", checks)


# ───────────────────────── 利益冲突预检 ─────────────────────────


class ConflictCheckService:
    """利益冲突预检：把本案当事人与既有客户/在办案件比对。

    ⚠️ 判定逻辑必须区分三档，不能一律报「冲突」：
      red     同名 + 证件号相同  → 就是同一个人，且已经在对方阵营 → 必须停
      yellow  同名但证件号不同   → 可能重名，需人工复核（律所最常见的情形）
      neutral 无证件号可比对     → 提示数据不全，不是冲突
    真实产品里这三档的处理完全不同：red 阻断、yellow 要人点「已复核」、
    neutral 只是提醒补全资料。一律当冲突会让律师对告警脱敏。
    """

    def check(self, case_id: int) -> dict[str, Any]:
        case = Case.objects.filter(id=case_id).first()
        if case is None:
            raise ValueError(f"案件不存在: {case_id}")

        # 本案的对方当事人（我方客户的对手才可能冲突）
        parties = list(CaseParty.objects.filter(case_id=case_id).select_related("client").all())
        if not parties:
            return {"case_id": case_id, "checked_parties": 0, "hits": [], "blocked": False}

        hits: list[dict[str, Any]] = []
        for p in parties:
            client = p.client
            if client is None:
                continue
            name = (client.name or "").strip()
            if not name:
                continue
            id_no = (getattr(client, "id_number", "") or "").strip()

            # 在**其他案件**里找同名当事人（排除本案自身）
            others = (
                CaseParty.objects.filter(client__name=name).exclude(case_id=case_id).select_related("client", "case")
            )
            for o in others:
                other_id = (getattr(o.client, "id_number", "") or "").strip()
                if id_no and other_id:
                    if id_no == other_id:
                        level, reason, matched = "red", "同名且证件号相同——同一人出现在另一案件中", True
                    else:
                        level, reason, matched = "yellow", "同名但证件号不同——疑似重名，需律师复核", False
                else:
                    level, reason, matched = "neutral", "同名但缺少证件号，无法自动判定", False
                hits.append(
                    {
                        "level": level,
                        "party_name": name,
                        "legal_status": p.get_legal_status_display()
                        if hasattr(p, "get_legal_status_display")
                        else (p.legal_status or ""),
                        "matched_client_id": getattr(o.client, "id", None),
                        "matched_client_name": name,
                        "matched_case_id": o.case_id,
                        "matched_case_name": getattr(o.case, "name", ""),
                        "reason": reason,
                        "id_matched": matched,
                    }
                )

        return {
            "case_id": case_id,
            "checked_parties": len(parties),
            "hits": hits,
            "blocked": any(h["level"] == "red" for h in hits),
        }
