from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.legal_research.models import LegalResearchResult, LegalResearchTask, LegalResearchTaskStatus
from apps.legal_research.services.executor import LegalResearchExecutor
from apps.organization.models import AccountCredential


class Command(BaseCommand):
    help = "回放法律检索标注样本并输出 precision/recall/F1 基线报告"
    DEFAULT_DATASET = "apps/legal_research/evaluation/baseline_cases.json"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dataset",
            type=str,
            default=self.DEFAULT_DATASET,
            help=f"标注样本集路径（默认: {self.DEFAULT_DATASET}）",
        )
        parser.add_argument(
            "--credential-id",
            type=int,
            default=None,
            help="覆盖样本里的 credential_id，统一使用该账号回放",
        )
        parser.add_argument(
            "--llm-model",
            type=str,
            default="",
            help="覆盖样本里的 llm_model",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="最多回放前 N 条样本，0 表示全部",
        )
        parser.add_argument(
            "--keep-artifacts",
            action="store_true",
            default=False,
            help="保留回放产生的任务与结果（默认清理）",
        )
        parser.add_argument(
            "--output-json",
            type=str,
            default="",
            help="将详细报告输出到 JSON 文件",
        )
        parser.add_argument(
            "--stop-on-error",
            action="store_true",
            default=False,
            help="遇到单条样本异常时立即停止",
        )
        parser.add_argument(
            "--write-template",
            action="store_true",
            default=False,
            help="将样本模板写入 --dataset 后退出",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dataset_path = Path(str(options["dataset"] or "").strip() or self.DEFAULT_DATASET)
        if options["write_template"]:
            self._write_template(path=dataset_path)
            self.stdout.write(self.style.SUCCESS(f"已写入样本模板: {dataset_path}"))
            return

        cases = self._load_cases(path=dataset_path)
        limit = int(options.get("limit") or 0)
        if limit > 0:
            cases = cases[:limit]
        if not cases:
            raise CommandError("样本为空，无法回放")

        credential_override = options.get("credential_id")
        llm_model_override = str(options.get("llm_model") or "").strip()
        keep_artifacts = bool(options.get("keep_artifacts"))
        stop_on_error = bool(options.get("stop_on_error"))

        executor = LegalResearchExecutor()
        reports: list[dict[str, Any]] = []
        total_tp = 0
        total_fp = 0
        total_fn = 0
        labeled_cases = 0
        errors = 0

        self.stdout.write(self.style.SUCCESS(f"开始回放: {dataset_path}"))
        self.stdout.write(f"样本数: {len(cases)}\n")

        for index, case in enumerate(cases, start=1):
            case_id = str(case.get("case_id") or f"case-{index:03d}")
            task: LegalResearchTask | None = None
            case_report: dict[str, Any]
            started = time.monotonic()
            try:
                credential = self._resolve_credential(case=case, credential_override=credential_override)
                task = self._create_task(
                    case=case,
                    credential=credential,
                    llm_model_override=llm_model_override,
                )
                run_payload = executor.run(task_id=str(task.id))
                task.refresh_from_db()

                results = list(
                    LegalResearchResult.objects.filter(task=task).order_by("rank").values(
                        "rank",
                        "source_doc_id",
                        "similarity_score",
                        "title",
                    )
                )
                predicted_doc_ids = [str(row["source_doc_id"]) for row in results]
                expected_doc_ids = self._to_str_list(case.get("expected_relevant_doc_ids"))
                tp, fp, fn = self._count_confusion(predicted_doc_ids=predicted_doc_ids, expected_doc_ids=expected_doc_ids)
                precision, recall, f1 = self._compute_prf(tp=tp, fp=fp, fn=fn)
                labeled = len(expected_doc_ids) > 0
                if labeled:
                    labeled_cases += 1
                    total_tp += tp
                    total_fp += fp
                    total_fn += fn

                elapsed_seconds = time.monotonic() - started
                case_report = {
                    "case_id": case_id,
                    "task_id": str(task.id),
                    "status": str(task.status),
                    "elapsed_seconds": round(elapsed_seconds, 2),
                    "scanned_count": int(task.scanned_count),
                    "candidate_count": int(task.candidate_count),
                    "matched_count": int(task.matched_count),
                    "predicted_doc_ids": predicted_doc_ids,
                    "expected_relevant_doc_ids": expected_doc_ids,
                    "tp": tp,
                    "fp": fp,
                    "fn": fn,
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                    "labeled": labeled,
                    "executor_payload": run_payload,
                }
                self.stdout.write(
                    f"[{index}/{len(cases)}] {case_id} -> status={task.status} "
                    f"pred={len(predicted_doc_ids)} exp={len(expected_doc_ids)} "
                    f"tp={tp} fp={fp} fn={fn} f1={f1:.3f}"
                )
            except Exception as exc:
                errors += 1
                elapsed_seconds = time.monotonic() - started
                case_report = {
                    "case_id": case_id,
                    "task_id": str(task.id) if task else "",
                    "status": "failed",
                    "elapsed_seconds": round(elapsed_seconds, 2),
                    "error": str(exc),
                }
                self.stderr.write(f"[{index}/{len(cases)}] {case_id} -> failed: {exc}")
                if stop_on_error:
                    if task is not None and not keep_artifacts:
                        task.delete()
                    break
            finally:
                reports.append(case_report)
                if task is not None and not keep_artifacts:
                    task.delete()

        precision, recall, f1 = self._compute_prf(tp=total_tp, fp=total_fp, fn=total_fn)
        summary = {
            "generated_at": timezone.now().isoformat(),
            "dataset_path": str(dataset_path),
            "total_cases": len(cases),
            "labeled_cases": labeled_cases,
            "errors": errors,
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
        report = {"summary": summary, "cases": reports}

        self.stdout.write("\n=== Benchmark Summary ===")
        self.stdout.write(f"labeled_cases: {labeled_cases}/{len(cases)}")
        self.stdout.write(f"errors: {errors}")
        self.stdout.write(f"tp/fp/fn: {total_tp}/{total_fp}/{total_fn}")
        self.stdout.write(f"precision: {precision:.4f}")
        self.stdout.write(f"recall:    {recall:.4f}")
        self.stdout.write(f"f1:        {f1:.4f}")

        output_json = str(options.get("output_json") or "").strip()
        if output_json:
            output_path = Path(output_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"报告已写入: {output_path}"))

    @classmethod
    def _load_cases(cls, *, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise CommandError(f"样本文件不存在: {path}（可先执行 --write-template）")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"样本文件解析失败: {exc}") from exc

        if isinstance(payload, list):
            cases = payload
        elif isinstance(payload, dict) and isinstance(payload.get("cases"), list):
            cases = payload["cases"]
        else:
            raise CommandError("样本文件格式错误：应为 list 或 {\"cases\": [...]} ")

        normalized: list[dict[str, Any]] = []
        for item in cases:
            if not isinstance(item, dict):
                continue
            if not str(item.get("keyword") or "").strip():
                raise CommandError("样本缺少 keyword")
            if not str(item.get("case_summary") or "").strip():
                raise CommandError("样本缺少 case_summary")
            normalized.append(item)
        return normalized

    @staticmethod
    def _write_template(*, path: Path) -> None:
        template = {
            "name": "legal_research_baseline_v1",
            "description": "请替换为你自己的标注样本。expected_relevant_doc_ids 为空时，该样本仅用于可用性回放，不参与 PRF 统计。",
            "cases": [
                {
                    "case_id": "sample-001",
                    "credential_id": 6,
                    "keyword": "佛山市顺德区人民法院 买卖合同纠纷",
                    "case_summary": (
                        "卖方违约转卖货物导致买方价差损失，"
                        "买方请求赔偿损失并承担违约责任。"
                    ),
                    "target_count": 3,
                    "max_candidates": 100,
                    "min_similarity_score": 0.82,
                    "llm_model": "Qwen/Qwen2.5-7B-Instruct",
                    "expected_relevant_doc_ids": [],
                }
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _resolve_credential(*, case: dict[str, Any], credential_override: int | None) -> AccountCredential:
        credential_id = credential_override or case.get("credential_id")
        if not credential_id:
            raise CommandError("缺少 credential_id（可通过 --credential-id 覆盖）")
        credential = AccountCredential.objects.select_related("lawyer").filter(id=credential_id).first()
        if credential is None:
            raise CommandError(f"账号不存在: credential_id={credential_id}")
        return credential

    @staticmethod
    def _create_task(
        *,
        case: dict[str, Any],
        credential: AccountCredential,
        llm_model_override: str,
    ) -> LegalResearchTask:
        return LegalResearchTask.objects.create(
            created_by=credential.lawyer,
            credential=credential,
            source=str(case.get("source") or "weike"),
            keyword=str(case.get("keyword") or "").strip(),
            case_summary=str(case.get("case_summary") or "").strip(),
            target_count=max(1, int(case.get("target_count") or 3)),
            max_candidates=max(1, int(case.get("max_candidates") or 100)),
            min_similarity_score=float(case.get("min_similarity_score") or 0.9),
            llm_backend="siliconflow",
            llm_model=str(llm_model_override or case.get("llm_model") or "").strip(),
            status=LegalResearchTaskStatus.PENDING,
        )

    @staticmethod
    def _to_str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(x).strip() for x in value if str(x).strip()]

    @classmethod
    def _count_confusion(cls, *, predicted_doc_ids: list[str], expected_doc_ids: list[str]) -> tuple[int, int, int]:
        predicted = set(cls._to_str_list(predicted_doc_ids))
        expected = set(cls._to_str_list(expected_doc_ids))
        tp = len(predicted.intersection(expected))
        fp = len(predicted - expected)
        fn = len(expected - predicted)
        return tp, fp, fn

    @staticmethod
    def _compute_prf(*, tp: int, fp: int, fn: int) -> tuple[float, float, float]:
        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        return precision, recall, f1
