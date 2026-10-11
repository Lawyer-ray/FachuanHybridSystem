"""合同文件夹扫描候选的 LLM 归档分类服务。

扫描完成后按需触发：将未匹配归档清单项的候选批量交给 LLM 分类，
返回建议经枚举校验后合并回扫描会话，用户仍需在弹窗中人工复核确认。
LLM 不可用或输出非法时保留关键词分类结果，不影响导入链路。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable
from uuid import UUID

from django.utils import timezone

from apps.contracts.models import ContractFolderScanSession, ContractFolderScanStatus
from apps.contracts.services.contract.integrations.archive_classifier import collect_archive_item_options
from apps.core.dependencies.core import build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.wiring import get_llm_service

logger = logging.getLogger(__name__)

LLMCompleteFn = Callable[..., str]

_VALID_CATEGORIES: tuple[str, ...] = (
    "contract_original",
    "supplementary_agreement",
    "invoice",
    "supervision_card",
    "case_material",
)
_CATEGORY_LABELS: dict[str, str] = {
    "contract_original": "合同正本（委托代理合同、服务合同本身）",
    "supplementary_agreement": "补充协议",
    "invoice": "发票",
    "supervision_card": "监督卡",
    "case_material": "案件材料（除上述四类外的全部文件）",
}
_ARCHIVE_CATEGORY_LABELS: dict[str, str] = {
    "litigation": "诉讼",
    "criminal": "刑事",
    "non_litigation": "常法（非诉）",
}

_BATCH_SIZE = 15
_MAX_TOKENS = 2000

_SYSTEM_PROMPT = (
    "你是律所合同归档材料分类助手。根据合同背景、文件名和所在文件夹，"
    "为每个文件选择材料类别和归档清单项。仅输出 JSON 数组，不要输出任何其他内容。"
    '数组元素结构：{"index": 文件序号, "category": 材料类别, "archive_item_code": 归档清单编号, '
    '"confidence": 0到1的数字, "reason": "15字以内理由"}。'
    "archive_item_code 仅在 category 为 case_material 时填写清单编号，其他类别填空字符串。"
)


def _default_llm_complete(*, prompt: str, system_prompt: str, model_id: str) -> str:
    response = get_llm_service().complete(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model_id or None,
        temperature=0.1,
        max_tokens=_MAX_TOKENS,
    )
    return str(getattr(response, "content", "") or "")


# ── 模块级纯函数（Service 层禁止静态方法装饰器，棘轮 test_four_layer_architecture 把关） ──


def select_targets(candidates: list[dict[str, Any]], *, scope: str) -> list[dict[str, Any]]:
    """选出待 AI 分类的候选：unmatched=未匹配清单项的案件材料，all=全部未跳过项。"""
    visible = [c for c in candidates if not c.get("skip_reason") and not c.get("already_imported")]
    if scope == "all":
        return visible
    return [
        c
        for c in visible
        if str(c.get("suggested_category") or "") == "case_material" and not str(c.get("archive_item_code") or "")
    ]


def build_prompt(
    *,
    batch: list[dict[str, Any]],
    contract_name: str,
    archive_category: str,
    item_options: list[dict[str, str]],
    scan_folder: str,
) -> str:
    category_label = _ARCHIVE_CATEGORY_LABELS.get(archive_category, archive_category)
    option_lines = "\n".join(f"- {opt['code']}：{opt['name']}" for opt in item_options)
    category_lines = "\n".join(f"- {code}：{_CATEGORY_LABELS[code]}" for code in _VALID_CATEGORIES)

    file_lines: list[str] = []
    for idx, item in enumerate(batch, start=1):
        folder = relative_parent_folder(source_path=str(item.get("source_path") or ""), scan_folder=scan_folder)
        location = f"［文件夹：{folder}］" if folder else ""
        keyword_hint = str(item.get("archive_item_name") or "")
        hint = f"（关键词分类：{keyword_hint}）" if keyword_hint else ""
        file_lines.append(f"{idx}. {location}文件名：{item.get('filename')}{hint}")

    return (
        f"合同名称：{contract_name or '（未命名）'}\n"
        f"归档分类：{category_label}\n"
        "业务背景：律师办案归档，请按文件语义选择最合适的类别与归档清单项。\n\n"
        f"材料类别（category 只能取以下值之一）：\n{category_lines}\n\n"
        "归档清单项（case_material 时 archive_item_code 只能取以下编号之一，"
        f"其他类别必须填空字符串）：\n{option_lines}\n\n"
        "文件列表：\n" + "\n".join(file_lines) + "\n\n"
        "请按文件列表序号输出 JSON 数组。"
    )


def relative_parent_folder(*, source_path: str, scan_folder: str) -> str:
    """取文件相对扫描根目录的父文件夹路径，供 LLM 参考目录语义。"""
    raw = source_path.replace("\\", "/")
    root = scan_folder.replace("\\", "/").rstrip("/")
    if root and raw.startswith(root + "/"):
        raw = raw[len(root) + 1 :]
    parent = raw.rsplit("/", 1)[0] if "/" in raw else ""
    return parent.lstrip("/")


def parse_llm_items(content: str) -> list[dict[str, Any]]:
    """解析 LLM 输出的 JSON 数组；解析失败返回空列表。"""
    text = str(content or "").strip()
    if not text:
        return []

    candidates: list[str] = [text]
    candidates.extend(re.findall(r"\[[\s\S]*\]", text))
    candidates.extend(re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE))
    for candidate in candidates:
        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, list):
            return [item for item in loaded if isinstance(item, dict)]
    return []


def apply_suggestion(
    candidate: dict[str, Any],
    suggestion: dict[str, Any],
    *,
    code_to_name: dict[str, str],
) -> bool:
    """校验并应用单条 AI 建议到候选；非法建议返回 False 且不改动候选。"""
    category = str(suggestion.get("category") or "").strip()
    if category not in _VALID_CATEGORIES:
        return False

    archive_item_code = str(suggestion.get("archive_item_code") or "").strip()
    if category == "case_material":
        if archive_item_code not in code_to_name:
            return False
    else:
        archive_item_code = ""

    try:
        confidence = min(1.0, max(0.0, float(suggestion.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0

    reason = str(suggestion.get("reason") or "").strip()[:60]
    candidate["suggested_category"] = category
    candidate["archive_item_code"] = archive_item_code
    candidate["archive_item_name"] = code_to_name.get(archive_item_code, "")
    candidate["confidence"] = confidence
    candidate["reason"] = f"AI：{reason}" if reason else "AI 分类建议"
    candidate["classified_by"] = "ai"
    candidate["selected"] = True
    return True


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _get_session(*, contract_id: int, session_id: UUID) -> ContractFolderScanSession:
    try:
        return ContractFolderScanSession.objects.get(id=session_id, contract_id=contract_id)
    except ContractFolderScanSession.DoesNotExist:
        raise NotFoundError("扫描会话不存在") from None


class ContractScanAIClassifyService:
    """扫描会话的 LLM 归档分类服务。"""

    _SCOPES: tuple[str, ...] = ("unmatched", "all")

    def __init__(self, *, llm_complete_fn: LLMCompleteFn | None = None) -> None:
        self._llm_complete = llm_complete_fn or _default_llm_complete

    # ── Public API ──────────────────────────────────────────────────────

    def start_ai_classify(
        self,
        *,
        contract_id: int,
        session_id: UUID,
        model_id: str = "",
        scope: str = "unmatched",
        started_by: Any | None = None,
    ) -> ContractFolderScanSession:  # pragma: no cover
        session = _get_session(contract_id=contract_id, session_id=session_id)
        if session.status != ContractFolderScanStatus.COMPLETED:
            raise ValidationException(
                message="仅扫描完成的会话可发起 AI 分类",
                errors={"status": session.status},
            )
        normalized_scope = scope if scope in self._SCOPES else "unmatched"

        ContractFolderScanSession.objects.filter(id=session.id).update(
            status=ContractFolderScanStatus.CLASSIFYING,
            error_message="",
            updated_at=timezone.now(),
        )
        try:
            task_id = build_task_submission_service().submit(
                "apps.contracts.services.contract.integrations.ai_classify_service.run_contract_scan_ai_classify_task",
                args=[str(session.id), str(model_id or ""), normalized_scope],
                task_name=f"contract_scan_ai_classify_{session.id}",
            )
        except Exception:
            # 任务投递失败时回滚状态，保留扫描结果可继续导入
            ContractFolderScanSession.objects.filter(id=session.id).update(
                status=ContractFolderScanStatus.COMPLETED,
                error_message="AI 分类任务投递失败",
                updated_at=timezone.now(),
            )
            raise

        ContractFolderScanSession.objects.filter(id=session.id).update(
            task_id=str(task_id),
            updated_at=timezone.now(),
        )
        session.refresh_from_db()
        logger.info(
            "contract_scan_ai_classify_submitted",
            extra={"contract_id": contract_id, "session_id": str(session.id), "scope": normalized_scope},
        )
        return session

    def run_ai_classify_task(self, *, session_id: str, model_id: str = "", scope: str = "unmatched") -> None:
        session = ContractFolderScanSession.objects.select_related("contract").filter(id=session_id).first()
        if not session:
            logger.warning("contract_scan_ai_classify_session_missing", extra={"session_id": session_id})
            return

        try:
            result = self._classify_session_candidates(session, model_id=model_id, scope=scope)
        except Exception as exc:
            logger.exception("contract_scan_ai_classify_failed", extra={"session_id": session_id})
            # 扫描结果仍然有效：回到 COMPLETED 让用户继续人工导入
            ContractFolderScanSession.objects.filter(id=session.id).update(
                status=ContractFolderScanStatus.COMPLETED,
                error_message=f"AI 分类失败：{type(exc).__name__}",
                updated_at=timezone.now(),
            )
            return

        ContractFolderScanSession.objects.filter(id=session.id).update(
            status=ContractFolderScanStatus.COMPLETED,
            progress=100,
            current_file="",
            error_message="",
            updated_at=timezone.now(),
            result_payload=result["payload"],
        )

    # ── 分类主流程 ─────────────────────────────────────────────────────

    def _classify_session_candidates(
        self,
        session: ContractFolderScanSession,
        *,
        model_id: str,
        scope: str,
    ) -> dict[str, Any]:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        payload = dict(session.result_payload or {})
        candidates = list(payload.get("candidates") or [])
        archive_category = str(payload.get("archive_category") or "")
        if not archive_category:
            archive_category = get_archive_category(getattr(session.contract, "case_type", ""))
        item_options = collect_archive_item_options(archive_category)
        code_to_name = {str(opt["code"]): str(opt["name"]) for opt in item_options}

        targets = select_targets(candidates, scope=scope)
        stats = {"targets": len(targets), "classified": 0, "invalid": 0, "llm_failed": 0}
        if targets:
            contract_name = str(getattr(session.contract, "name", "") or "")
            scan_folder = str((payload.get("scan_scope") or {}).get("scan_folder") or "")
            self._run_batches(
                session_id=session.id,
                targets=targets,
                contract_name=contract_name,
                archive_category=archive_category,
                item_options=item_options,
                scan_folder=scan_folder,
                model_id=model_id,
                code_to_name=code_to_name,
                stats=stats,
            )

        payload["ai_classify_result"] = {
            "model": str(model_id or ""),
            "scope": scope,
            **stats,
            "finished_at": timezone.now().isoformat(),
        }
        return {"payload": payload}

    def _run_batches(
        self,
        *,
        session_id: UUID,
        targets: list[dict[str, Any]],
        contract_name: str,
        archive_category: str,
        item_options: list[dict[str, str]],
        scan_folder: str,
        model_id: str,
        code_to_name: dict[str, str],
        stats: dict[str, int],
    ) -> None:
        total_batches = (len(targets) + _BATCH_SIZE - 1) // _BATCH_SIZE
        for batch_idx in range(total_batches):
            batch = targets[batch_idx * _BATCH_SIZE : (batch_idx + 1) * _BATCH_SIZE]
            index_map = dict(enumerate(batch, start=1))
            ContractFolderScanSession.objects.filter(id=session_id).update(
                progress=min(90, 10 + int((batch_idx / max(total_batches, 1)) * 80)),
                current_file=str(batch[0].get("filename") or ""),
                updated_at=timezone.now(),
            )
            prompt = build_prompt(
                batch=batch,
                contract_name=contract_name,
                archive_category=archive_category,
                item_options=item_options,
                scan_folder=scan_folder,
            )
            try:
                content = self._llm_complete(prompt=prompt, system_prompt=_SYSTEM_PROMPT, model_id=model_id)
            except Exception:
                logger.exception(
                    "contract_scan_ai_classify_llm_failed",
                    extra={"session_id": str(session_id), "batch": batch_idx + 1},
                )
                stats["llm_failed"] += len(batch)
                continue

            for suggestion in parse_llm_items(content):
                candidate = index_map.get(_to_int(suggestion.get("index")))
                if candidate is None or not apply_suggestion(candidate, suggestion, code_to_name=code_to_name):
                    stats["invalid"] += 1
                else:
                    stats["classified"] += 1


def run_contract_scan_ai_classify_task(session_id: str, model_id: str = "", scope: str = "unmatched") -> None:
    """Django-Q 任务入口。"""
    ContractScanAIClassifyService().run_ai_classify_task(session_id=session_id, model_id=model_id, scope=scope)
