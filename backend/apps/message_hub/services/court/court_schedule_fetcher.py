"""一张网庭审日程 fetcher — 拉取 zhrl/list 接口数据写入 Reminder(HEARING)。"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.message_hub.models import SyncStatus
from apps.message_hub.services.base import MessageFetcher
from apps.message_hub.services.court.court_fetcher import (
    _acquire_token,
    _api_post,
    _invalidate_token,
    _mark_failed,
    _mark_success,
)

if TYPE_CHECKING:
    from apps.message_hub.models import MessageSource

logger = logging.getLogger("apps.message_hub")

_ZHRL_API_URL = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-xxfw/api/v1/zhrl/list"
_PAGE_SIZE = 20


@dataclass(frozen=True)
class ParsedHearing:
    """解析后的庭审记录 DTO。"""

    source_id: str  # bh — 排期唯一 ID（去重键）
    content: str  # rcbt — 日程标题
    due_at: datetime  # kssj — 开始时间
    case_id: int | None  # 关联的案件 ID（可能为 None）
    match_strategy: str  # "exact" | "party" | "none"
    metadata: dict[str, Any] = field(default_factory=dict)


def _parse_datetime(s: str) -> datetime:
    """解析 API 返回的时间字符串，格式: '2026-05-29 16:30'。"""
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        return timezone.make_aware(dt)
    except (ValueError, TypeError):
        return timezone.now()


# ---------------------------------------------------------------------------
# rcbt 分词 — 提取当事人名称
# ---------------------------------------------------------------------------

_CASE_SUFFIX = "一案"


def _extract_party_names(rcbt: str) -> list[str]:
    """
    从 rcbt 日程标题中分词提取当事人名称。

    规则:
    1. 去掉末尾「一案」后缀
    2. 以「与」分割 → 原告部分 / 被告部分
    3. 被告部分以「,」(全角或半角)分割
    4. 每个片段去除末尾案由噪声，提取有效当事人名称

    示例:
      "佛山市升平百货有限公司与佛山市仲满金属材料有限公司,郑汝钋,石莹追偿权纠纷一案"
      → ["佛山市升平百货有限公司", "佛山市仲满金属材料有限公司", "郑汝钋", "石莹"]
    """
    if not rcbt:
        return []

    text = rcbt.strip()
    if text.endswith(_CASE_SUFFIX):
        text = text[: -len(_CASE_SUFFIX)]

    # 以「与」分割为原告和被告部分
    if "与" not in text:
        return []

    plaintiff_part, _, defendant_part = text.partition("与")

    names: list[str] = []

    # 原告部分（通常不含案由噪声）
    for name in _split_by_comma(plaintiff_part):
        name = name.strip()
        if _is_valid_party_name(name):
            names.append(name)

    # 被告部分 — 每个片段可能带案由后缀，需剥离
    for segment in _split_by_comma(defendant_part):
        segment = segment.strip()
        if not segment:
            continue
        # 尝试剥离末尾的案由部分，提取当事人名称
        extracted = _extract_name_from_segment(segment)
        for name in extracted:
            if _is_valid_party_name(name) and name not in names:
                names.append(name)

    return names


def _extract_name_from_segment(segment: str) -> list[str]:
    """
    从可能混有案由的片段中提取当事人名称。

    例如:
      "汪达买卖合同纠纷" → ["汪达"]
      "石莹追偿权纠纷" → ["石莹"]
      "佛山市仲满金属材料有限公司" → ["佛山市仲满金属材料有限公司"]
      "郑汝钋" → ["郑汝钋"]
      "国家税务总局海南省税务局××（行政行为）及行政复议" → ["国家税务总局海南省税务局××"]
    """
    # 如果已经是有效当事人名称，直接返回
    if _is_valid_party_name(segment):
        return [segment]

    # 尝试剥离末尾案由部分
    # 策略: 找到最后一个案由关键词的位置，截取其前面的部分
    stripped = _strip_case_cause_suffix(segment)
    if stripped and _is_valid_party_name(stripped):
        return [stripped]

    # 如果剥离后仍无效，可能是多个名称粘在一起，尝试其他策略
    # 例如 "郑建云,曾强民间借贷纠纷" 在上层已经按逗号分割
    if _is_valid_party_name(segment):
        return [segment]

    return []


def _strip_case_cause_suffix(text: str) -> str:
    """
    剥离文本末尾的案由后缀，返回剩余的当事人名称部分。

    优先匹配最长的案由后缀，例如 "买卖合同纠纷" 优先于 "纠纷"。

    示例:
      "汪达买卖合同纠纷" → "汪达"
      "石莹追偿权纠纷" → "石莹"
      "佛山市仲满金属材料有限公司" → "佛山市仲满金属材料有限公司"（不变）
    """
    # 从长到短尝试剥离案由后缀
    cause_suffixes = [
        "买卖合同纠纷",
        "房屋租赁合同纠纷",
        "租赁合同纠纷",
        "民间借贷纠纷",
        "追偿权纠纷",
        "合同纠纷",
        "侵权纠纷",
        "劳动纠纷",
        "行政纠纷",
        "借贷纠纷",
        "租赁纠纷",
        "保险纠纷",
        "票据纠纷",
        "证券纠纷",
        "担保纠纷",
        "抵押纠纷",
        "质押纠纷",
        "海事纠纷",
        "破产纠纷",
        "知识产权纠纷",
        "垄断纠纷",
        "竞争纠纷",
        "信托纠纷",
        "不当得利纠纷",
        "无因管理纠纷",
        "侵权责任纠纷",
        "违约责任纠纷",
        "行政行为及行政复议",
        "纠纷",
        "侵权",
        "违约",
    ]
    for suffix in cause_suffixes:
        if text.endswith(suffix):
            stripped = text[: -len(suffix)].strip()
            if stripped:
                return stripped
    return text


# 常见案由关键词（用于过滤噪声片段）
_CASE_CAUSE_KEYWORDS = (
    "纠纷",
    "侵权",
    "违约",
    "犯罪",
    "违法",
    "合同",
    "借贷",
    "买卖",
    "租赁",
    "劳动",
    "行政",
    "执行",
    "保全",
    "诉讼",
    "仲裁",
    "赔偿",
    "担保",
    "抵押",
    "质押",
    "留置",
    "不当得利",
    "无因管理",
    "知识产权",
    "竞争",
    "垄断",
    "信托",
    "保险",
    "票据",
    "证券",
    "破产",
    "海事",
)


def _is_valid_party_name(name: str) -> bool:
    """判断是否为有效的当事人名称（过滤案由噪声）。"""
    if not name or len(name) < 2:
        return False
    # 纯案由片段（如「追偿权纠纷」「买卖合同纠纷」）通常不含组织后缀或人名特征
    # 策略: 如果名称仅由案由关键词和少量修饰组成（≤4字且含案由关键词），过滤掉
    if len(name) <= 6 and any(kw in name for kw in _CASE_CAUSE_KEYWORDS):
        return False
    # 组织后缀 — 一定是有效当事人
    org_suffixes = (
        "有限公司",
        "股份公司",
        "公司",
        "事务所",
        "事务所",
        "银行",
        "集团",
        "医院",
        "学校",
        "局",
        "厅",
        "部",
        "委",
        "院",
        "所",
        "中心",
        "合作社",
    )
    if any(name.endswith(s) for s in org_suffixes):
        return True
    # 人名特征: 2-4 个中文字符且不含案由关键词
    if 2 <= len(name) <= 4 and not any(kw in name for kw in _CASE_CAUSE_KEYWORDS):
        return True
    # 较长的名称通常也是有效当事人
    if len(name) > 6:
        # 排除以案由关键词结尾的纯案由描述
        if not any(name.endswith(kw) for kw in ("纠纷", "侵权", "违约", "一案")):
            return True
    return False


def _split_by_comma(text: str) -> list[str]:
    """以全角或半角逗号分割文本。"""
    return text.replace("，", ",").split(",")


# ---------------------------------------------------------------------------
# 案件关联策略
# ---------------------------------------------------------------------------


def _find_case_id(record: dict[str, Any]) -> tuple[int | None, str]:
    """
    二级匹配策略查找关联的 Case ID。

    Returns:
        (case_id, match_strategy) — match_strategy 为 "exact"/"party"/"none"
    """
    # S1: 正式案号精确匹配
    ah = record.get("ah")
    if ah:
        case_id = _match_by_case_number(str(ah))
        if case_id is not None:
            return case_id, "exact"

    # S2: 当事人名称匹配
    rcbt = record.get("rcbt", "")
    if rcbt:
        party_names = _extract_party_names(str(rcbt))
        if party_names:
            case_id = _match_by_party_names(party_names)
            if case_id is not None:
                return case_id, "party"

    # S3: 不关联
    return None, "none"


def _match_by_case_number(ah: str) -> int | None:
    """S1: 用正式案号精确匹配 CaseNumber.number → Case。"""
    from apps.cases.models import CaseNumber

    cn = CaseNumber.objects.filter(number=ah).select_related("case").first()
    if cn and cn.case and cn.case.pk:
        return int(cn.case.pk)
    return None


def _match_by_party_names(party_names: list[str]) -> int | None:
    """
    S2: 用当事人名称匹配 Client → CaseParty → Case。

    逻辑: 找到所有命中的 case_id 集合，取交集。
    交集恰好为 1 个 → 返回该 case_id
    交集为 0 或 >1 → 返回 None（宁缺毋滥）
    """
    from apps.cases.models import CaseParty
    from apps.client.models import Client

    case_id_sets: list[set[int]] = []

    for name in party_names:
        client = Client.objects.filter(name=name).first()
        if not client:
            continue
        case_ids: set[int] = set(CaseParty.objects.filter(client=client).values_list("case_id", flat=True))
        if case_ids:
            case_id_sets.append(case_ids)

    if not case_id_sets:
        return None

    # 取交集
    intersection = case_id_sets[0]
    for s in case_id_sets[1:]:
        intersection = intersection & s

    if len(intersection) == 1:
        return intersection.pop()
    return None


# ---------------------------------------------------------------------------
# Fetcher 主体
# ---------------------------------------------------------------------------


class CourtScheduleFetcher(MessageFetcher):
    """一张网（zxfw.court.gov.cn）庭审日程拉取器。"""

    def fetch_new_messages(self, source: MessageSource) -> int:
        credential_id = source.credential.pk
        try:
            token = _acquire_token(credential_id)
        except Exception as e:
            _mark_failed(source, str(e))
            raise

        try:
            return self._fetch_with_token(source, token, credential_id)
        except PermissionError:
            logger.warning("一张网庭审日程: Token 过期，重新登录")
            _invalidate_token(credential_id)
            try:
                token = _acquire_token(credential_id)
                return self._fetch_with_token(source, token, credential_id)
            except Exception as e:
                _mark_failed(source, str(e))
                raise
        except Exception as e:
            _mark_failed(source, str(e))
            raise

    def _fetch_with_token(self, source: MessageSource, token: str, credential_id: int) -> int:
        new_count = 0
        records = self._fetch_all_pages(token)
        lawyer_name = self._get_lawyer_name(source)
        logger.info("一张网庭审日程: 共拉取 %d 条排期记录", len(records))

        for record in records:
            bh = record.get("bh", "")
            if not bh:
                continue
            if self._upsert_reminder(source, record, lawyer_name):
                new_count += 1

        _mark_success(source)
        return new_count

    def _fetch_all_pages(self, token: str) -> list[dict[str, Any]]:
        """分页拉取所有庭审记录。"""
        all_records: list[dict[str, Any]] = []
        body = _api_post(
            _ZHRL_API_URL,
            token,
            {"anyday": "", "isRc": 2, "option": 2, "pageNo": 1, "pageSize": _PAGE_SIZE},
        )
        total_rows = body.get("totalRows", 0)
        data = body.get("data", [])
        all_records.extend(data)

        total_pages = max(1, math.ceil(total_rows / _PAGE_SIZE))
        logger.info("一张网庭审日程: totalRows=%d, %d 页", total_rows, total_pages)

        for page_num in range(2, total_pages + 1):
            try:
                body = _api_post(
                    _ZHRL_API_URL,
                    token,
                    {"anyday": "", "isRc": 2, "option": 2, "pageNo": page_num, "pageSize": _PAGE_SIZE},
                )
                all_records.extend(body.get("data", []))
            except Exception as e:
                logger.error("一张网庭审日程: 第 %d 页拉取失败: %s", page_num, e)

        return all_records

    @staticmethod
    def _get_lawyer_name(source: MessageSource) -> str:
        """从 source.credential.lawyer 获取律师姓名。"""
        try:
            return str(source.credential.lawyer.real_name or source.credential.lawyer.username or "")
        except Exception:
            return ""

    def _upsert_reminder(self, source: MessageSource, record: dict[str, Any], lawyer_name: str) -> bool:
        """
        创建或更新 Reminder，返回是否为新建。

        去重键: (metadata__source_id, metadata__source_credential_id)
        同一庭审、不同律师各自创建独立的 Reminder。
        """
        from apps.reminders.models import Reminder, ReminderType

        bh = record.get("bh", "")
        kssj = record.get("kssj", "")
        rcbt = record.get("rcbt", "") or _("(无标题)")

        if not kssj:
            logger.warning("一张网庭审日程: 跳过无时间的记录 bh=%s", bh)
            return False

        due_at = _parse_datetime(kssj)
        case_id, match_strategy = _find_case_id(record)
        credential_id = source.credential.pk

        # 去重查询：同一庭审 + 同一律师账号
        existing = Reminder.objects.filter(
            reminder_type=ReminderType.HEARING,
            metadata__source_id=bh,
            metadata__source_credential_id=credential_id,
        ).first()

        metadata: dict[str, Any] = {
            "source_id": bh,
            "source_type": "court_schedule",
            "source_credential_id": source.credential.pk,
            "lawyer_name": lawyer_name,
            "courtroom": record.get("rcdd", ""),
            "end_time": record.get("jssj", ""),
            "time_range": record.get("sj", ""),
            "hearing_type": record.get("lx", ""),
            "fydm": record.get("fydm", ""),
            "ajbs": record.get("ajbs", ""),
            "ah": record.get("ah"),
            "match_strategy": match_strategy,
        }

        if existing:
<<<<<<< Updated upstream
            # 仅在关键字段发生变更时才更新，避免无差异写入导致重复更新日志
            if (
                existing.content == rcbt
                and existing.due_at == due_at
                and existing.case_id == case_id
                and existing.metadata == metadata
            ):
                logger.debug("一张网庭审日程: 记录无变化，跳过更新 bh=%s, credential=%s", bh, credential_id)
                return False

            existing.content = rcbt
            existing.due_at = due_at
            existing.case_id = case_id
            existing.metadata = metadata
            existing.save(update_fields=["content", "due_at", "case_id", "metadata", "updated_at"])
            logger.info("一张网庭审日程: 更新已有记录 bh=%s, credential=%s", bh, credential_id)
=======
            # 仅在字段发生变化时更新，避免每次同步都触发无意义写入
            changed_fields: list[str] = []

            if existing.content != rcbt:
                existing.content = rcbt
                changed_fields.append("content")

            if existing.due_at != due_at:
                existing.due_at = due_at
                changed_fields.append("due_at")

            if existing.case_id != case_id:
                existing.case_id = case_id
                changed_fields.append("case_id")

            if existing.metadata != metadata:
                existing.metadata = metadata
                changed_fields.append("metadata")

            if changed_fields:
                existing.save(update_fields=[*changed_fields, "updated_at"])
                logger.info(
                    "一张网庭审日程: 更新已有记录 bh=%s, credential=%s, fields=%s",
                    bh,
                    credential_id,
                    ",".join(changed_fields),
                )
            else:
                logger.info("一张网庭审日程: 已存在且无变更 bh=%s, credential=%s", bh, credential_id)
>>>>>>> Stashed changes
            return False

        Reminder.objects.create(
            reminder_type=ReminderType.HEARING,
            content=rcbt,
            due_at=due_at,
            case_id=case_id,
            metadata=metadata,
        )
        logger.info(
            "一张网庭审日程: 新增记录 bh=%s, credential=%s, case_id=%s, strategy=%s",
            bh,
            credential_id,
            case_id,
            match_strategy,
        )
        return True
