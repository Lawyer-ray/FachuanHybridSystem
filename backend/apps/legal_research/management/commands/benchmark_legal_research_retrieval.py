from __future__ import annotations

import csv
import json
import re
import time
from contextlib import contextmanager
from dataclasses import replace
from itertools import product
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.legal_research.models import LegalResearchResult, LegalResearchTask, LegalResearchTaskStatus
from apps.legal_research.services.executor import LegalResearchExecutor
from apps.legal_research.services.tuning_config import LegalResearchTuningConfig
from apps.organization.models import AccountCredential


class Command(BaseCommand):
    help = "回放法律检索标注样本并输出 precision/recall/F1 基线报告"
    DEFAULT_DATASET = "apps/legal_research/evaluation/baseline_cases.json"
    QUERY_TYPE_PRIMARY = "primary"
    QUERY_TYPE_EXPANSION = "expansion"
    QUERY_TYPE_FEEDBACK = "feedback"
    QUERY_TYPE_OTHER = "other"
    QUERY_TYPE_ORDER = (
        QUERY_TYPE_PRIMARY,
        QUERY_TYPE_EXPANSION,
        QUERY_TYPE_FEEDBACK,
        QUERY_TYPE_OTHER,
    )
    QUERY_TYPE_LABELS = {
        QUERY_TYPE_PRIMARY: "主查询",
        QUERY_TYPE_EXPANSION: "扩展查询",
        QUERY_TYPE_FEEDBACK: "反馈查询",
        QUERY_TYPE_OTHER: "其他",
    }

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
            "--min-labeled-cases",
            type=int,
            default=1,
            help="最少标注样本数（默认1；设为0可跳过校验）",
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
            "--output-csv",
            type=str,
            default="",
            help="将场景汇总输出到 CSV 文件（多场景时推荐）",
        )
        parser.add_argument(
            "--similarity-local-cache-max-size",
            type=int,
            default=0,
            help="单场景覆盖：LEGAL_RESEARCH_SIMILARITY_LOCAL_CACHE_MAX_SIZE（0=不覆盖）",
        )
        parser.add_argument(
            "--semantic-local-cache-max-size",
            type=int,
            default=0,
            help="单场景覆盖：LEGAL_RESEARCH_SEMANTIC_VECTOR_LOCAL_CACHE_MAX_SIZE（0=不覆盖）",
        )
        parser.add_argument(
            "--weike-session-restrict-cooldown-seconds",
            type=int,
            default=0,
            help="单场景覆盖：LEGAL_RESEARCH_WEIKE_SESSION_RESTRICT_COOLDOWN_SECONDS（0=不覆盖）",
        )
        parser.add_argument(
            "--ab-similarity-local-cache-sizes",
            type=str,
            default="",
            help="A/B矩阵：相似度本地缓存上限列表（逗号分隔，如 512,1024,2048）",
        )
        parser.add_argument(
            "--ab-semantic-local-cache-sizes",
            type=str,
            default="",
            help="A/B矩阵：语义向量本地缓存上限列表（逗号分隔）",
        )
        parser.add_argument(
            "--ab-weike-cooldown-seconds",
            type=str,
            default="",
            help="A/B矩阵：私有数据源 C_001_009 冷却秒数列表（逗号分隔）",
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

        min_labeled_cases = max(0, int(options.get("min_labeled_cases") or 0))
        labeled_cases_in_dataset = self._count_labeled_cases(cases=cases)
        if min_labeled_cases > 0 and labeled_cases_in_dataset < min_labeled_cases:
            raise CommandError(

                    f"标注样本不足: {labeled_cases_in_dataset}/{len(cases)}，"
                    f"要求至少 {min_labeled_cases} 条。"
                    "可用 --min-labeled-cases 0 跳过校验。"

            )

        credential_override = options.get("credential_id")
        llm_model_override = str(options.get("llm_model") or "").strip()
        keep_artifacts = bool(options.get("keep_artifacts"))
        stop_on_error = bool(options.get("stop_on_error"))

        scenarios = self._build_ab_scenarios(options=options)
        self.stdout.write(self.style.SUCCESS(f"开始回放: {dataset_path}"))
        self.stdout.write(f"样本数: {len(cases)}")
        self.stdout.write(f"标注样本: {labeled_cases_in_dataset}/{len(cases)}")
        if len(scenarios) > 1:
            self.stdout.write(f"场景数: {len(scenarios)}")
        self.stdout.write("")

        scenario_reports: list[dict[str, Any]] = []
        for idx, scenario in enumerate(scenarios, start=1):
            scenario_id = str(scenario.get("scenario_id") or f"scenario-{idx}")
            overrides = dict(scenario.get("overrides") or {})
            self.stdout.write(f"=== 场景 {idx}/{len(scenarios)}: {scenario_id} ===")
            if overrides:
                self.stdout.write(f"overrides: {json.dumps(overrides, ensure_ascii=False, sort_keys=True)}")
            with self._temporary_tuning_overrides(overrides):
                report = self._run_single_benchmark(
                    dataset_path=dataset_path,
                    cases=cases,
                    credential_override=credential_override,
                    llm_model_override=llm_model_override,
                    keep_artifacts=keep_artifacts,
                    stop_on_error=stop_on_error,
                )
            scenario_reports.append(
                {
                    "scenario_id": scenario_id,
                    "overrides": overrides,
                    "summary": report["summary"],
                    "cases": report["cases"],
                }
            )
            self.stdout.write("")

        output_json = str(options.get("output_json") or "").strip()
        output_csv = str(options.get("output_csv") or "").strip()
        if len(scenarios) == 1:
            final_report = {
                "summary": scenario_reports[0]["summary"],
                "cases": scenario_reports[0]["cases"],
            }
            if output_json:
                output_path = Path(output_json)
                self._write_json_report(path=output_path, payload=final_report)
                self.stdout.write(self.style.SUCCESS(f"报告已写入: {output_path}"))
            if output_csv:
                self._write_summary_csv(path=Path(output_csv), scenario_reports=scenario_reports)
            return

        matrix_report = {
            "generated_at": timezone.now().isoformat(),
            "dataset_path": str(dataset_path),
            "scenario_count": len(scenario_reports),
            "scenarios": scenario_reports,
        }
        self.stdout.write("=== Matrix Summary ===")
        for item in scenario_reports:
            summary = dict(item.get("summary") or {})
            primary_contribution = self._query_type_metric_value(
                summary=summary,
                query_type=self.QUERY_TYPE_PRIMARY,
                key="contribution_rate",
            )
            expansion_contribution = self._query_type_metric_value(
                summary=summary,
                query_type=self.QUERY_TYPE_EXPANSION,
                key="contribution_rate",
            )
            feedback_contribution = self._query_type_metric_value(
                summary=summary,
                query_type=self.QUERY_TYPE_FEEDBACK,
                key="contribution_rate",
            )
            self.stdout.write(
                f"{item['scenario_id']}: f1={float(summary.get('f1', 0.0)):.4f} "
                f"precision={float(summary.get('precision', 0.0)):.4f} "
                f"recall={float(summary.get('recall', 0.0)):.4f} "
                f"errors={int(summary.get('errors', 0))} "
                f"贡献率(primary/expansion/feedback)="
                f"{primary_contribution:.4f}/{expansion_contribution:.4f}/{feedback_contribution:.4f}"
            )

        if output_json:
            output_path = Path(output_json)
            self._write_json_report(path=output_path, payload=matrix_report)
            self.stdout.write(self.style.SUCCESS(f"矩阵报告已写入: {output_path}"))
        if output_csv:
            self._write_summary_csv(path=Path(output_csv), scenario_reports=scenario_reports)

    def _run_single_benchmark(
        self,
        *,
        dataset_path: Path,
        cases: list[dict[str, Any]],
        credential_override: int | None,
        llm_model_override: str,
        keep_artifacts: bool,
        stop_on_error: bool,
    ) -> dict[str, Any]:
        executor = LegalResearchExecutor()
        reports: list[dict[str, Any]] = []
        total_tp = 0
        total_fp = 0
        total_fn = 0
        labeled_cases = 0
        errors = 0
        query_type_stats: dict[str, dict[str, int]] = {}

        for index, case in enumerate(cases, start=1):
            case_id = str(case.get("case_id") or f"case-{index:03d}")
            query_type = self._normalize_query_type(case.get("query_type"))
            query_type_metric = query_type_stats.setdefault(query_type, self._init_query_type_metric())
            query_type_metric["total_cases"] += 1
            task: LegalResearchTask | None = None
            case_report: dict[str, Any] = {
                "case_id": case_id,
                "query_type": query_type,
                "task_id": "",
                "status": "failed",
                "elapsed_seconds": 0.0,
                "error": "unknown_error",
            }
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
                    query_type_metric["labeled_cases"] += 1
                    query_type_metric["tp"] += tp
                    query_type_metric["fp"] += fp
                    query_type_metric["fn"] += fn

                elapsed_seconds = time.monotonic() - started
                case_report = {
                    "case_id": case_id,
                    "query_type": query_type,
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
            except KeyboardInterrupt as exc:
                errors += 1
                elapsed_seconds = time.monotonic() - started
                case_report = {
                    "case_id": case_id,
                    "query_type": query_type,
                    "task_id": str(task.id) if task else "",
                    "status": "interrupted",
                    "elapsed_seconds": round(elapsed_seconds, 2),
                    "error": str(exc) or "KeyboardInterrupt",
                }
                self.stderr.write(f"[{index}/{len(cases)}] {case_id} -> interrupted by user")
                raise
            except Exception as exc:
                errors += 1
                query_type_metric["errors"] += 1
                elapsed_seconds = time.monotonic() - started
                case_report = {
                    "case_id": case_id,
                    "query_type": query_type,
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
        query_type_metrics = self._build_query_type_metrics(
            query_type_stats=query_type_stats,
            total_tp=total_tp,
            total_cases=len(cases),
            labeled_cases=labeled_cases,
        )
        summary = {
            "generated_at": timezone.now().isoformat(),
            "dataset_path": str(dataset_path),
            "total_cases": len(cases),
            "labeled_cases": labeled_cases,
            "labeled_ratio": round(float(labeled_cases / max(1, len(cases))), 4),
            "errors": errors,
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "query_type_metrics": query_type_metrics,
        }
        self.stdout.write("=== Benchmark Summary ===")
        self.stdout.write(f"labeled_cases: {labeled_cases}/{len(cases)}")
        self.stdout.write(f"labeled_ratio: {summary['labeled_ratio']:.4f}")
        self.stdout.write(f"errors: {errors}")
        self.stdout.write(f"tp/fp/fn: {total_tp}/{total_fp}/{total_fn}")
        self.stdout.write(f"precision: {precision:.4f}")
        self.stdout.write(f"recall:    {recall:.4f}")
        self.stdout.write(f"f1:        {f1:.4f}")
        if query_type_metrics:
            self.stdout.write("=== Query Type Contribution ===")
            for metric in query_type_metrics:
                self.stdout.write(

                        f"{metric['query_type']}({metric['query_type_label']}): "
                        f"cases={metric['total_cases']} labeled={metric['labeled_cases']} "
                        f"tp/fp/fn={metric['tp']}/{metric['fp']}/{metric['fn']} "
                        f"f1={float(metric['f1']):.4f} "
                        f"贡献率={float(metric['contribution_rate']):.4f}"

                )
        return {"summary": summary, "cases": reports}

    @staticmethod
    def _count_labeled_cases(*, cases: list[dict[str, Any]]) -> int:
        return sum(1 for case in cases if len(Command._to_str_list(case.get("expected_relevant_doc_ids"))) > 0)

    @staticmethod
    def _init_query_type_metric() -> dict[str, int]:
        return {
            "total_cases": 0,
            "labeled_cases": 0,
            "errors": 0,
            "tp": 0,
            "fp": 0,
            "fn": 0,
        }

    @classmethod
    def _normalize_query_type(cls, raw: Any) -> str:
        text = str(raw or "").strip().lower()
        if not text:
            return cls.QUERY_TYPE_OTHER
        token = re.sub(r"[\s_\-]+", "", text)
        if token in {"primary", "main", "base", "主查询", "主检索", "主召回"}:
            return cls.QUERY_TYPE_PRIMARY
        if token in {"expansion", "expanded", "intent", "扩展", "扩展查询", "意图扩展"}:
            return cls.QUERY_TYPE_EXPANSION
        if token in {"feedback", "反馈", "反馈查询", "回馈"}:
            return cls.QUERY_TYPE_FEEDBACK
        return cls.QUERY_TYPE_OTHER

    @classmethod
    def _query_type_label(cls, query_type: str) -> str:
        return cls.QUERY_TYPE_LABELS.get(query_type, query_type)

    @classmethod
    def _build_query_type_metrics(
        cls,
        *,
        query_type_stats: dict[str, dict[str, int]],
        total_tp: int,
        total_cases: int,
        labeled_cases: int,
    ) -> list[dict[str, Any]]:
        if not query_type_stats:
            return []

        ordered: list[str] = [query_type for query_type in cls.QUERY_TYPE_ORDER if query_type in query_type_stats]
        extras = sorted(query_type for query_type in query_type_stats if query_type not in cls.QUERY_TYPE_ORDER)
        ordered.extend(extras)

        out: list[dict[str, Any]] = []
        for query_type in ordered:
            stats = query_type_stats.get(query_type) or {}
            tp = int(stats.get("tp", 0))
            fp = int(stats.get("fp", 0))
            fn = int(stats.get("fn", 0))
            precision, recall, f1 = cls._compute_prf(tp=tp, fp=fp, fn=fn)
            total_cases_for_type = int(stats.get("total_cases", 0))
            labeled_cases_for_type = int(stats.get("labeled_cases", 0))
            errors_for_type = int(stats.get("errors", 0))
            out.append(
                {
                    "query_type": query_type,
                    "query_type_label": cls._query_type_label(query_type),
                    "total_cases": total_cases_for_type,
                    "total_case_ratio": round(total_cases_for_type / max(1, total_cases), 4),
                    "labeled_cases": labeled_cases_for_type,
                    "labeled_case_ratio": (
                        round(labeled_cases_for_type / max(1, labeled_cases), 4) if labeled_cases > 0 else 0.0
                    ),
                    "errors": errors_for_type,
                    "tp": tp,
                    "fp": fp,
                    "fn": fn,
                    "precision": round(precision, 4),
                    "recall": round(recall, 4),
                    "f1": round(f1, 4),
                    "contribution_rate": round(tp / max(1, total_tp), 4) if total_tp > 0 else 0.0,
                }
            )
        return out

    @staticmethod
    def _query_type_metric_value(*, summary: dict[str, Any], query_type: str, key: str) -> float:
        metrics = summary.get("query_type_metrics")
        if not isinstance(metrics, list):
            return 0.0
        for item in metrics:
            if not isinstance(item, dict):
                continue
            if str(item.get("query_type") or "").strip() != query_type:
                continue
            try:
                return float(item.get(key, 0.0))
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    @staticmethod
    def _write_json_report(*, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_summary_csv(self, *, path: Path, scenario_reports: list[dict[str, Any]]) -> None:
        fieldnames = [
            "scenario_id",
            "similarity_local_cache_max_size",
            "semantic_vector_local_cache_max_size",
            "weike_session_restrict_cooldown_seconds",
            "total_cases",
            "labeled_cases",
            "labeled_ratio",
            "errors",
            "tp",
            "fp",
            "fn",
            "precision",
            "recall",
            "f1",
            "primary_contribution_rate",
            "expansion_contribution_rate",
            "feedback_contribution_rate",
            "other_contribution_rate",
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in scenario_reports:
                summary = dict(item.get("summary") or {})
                overrides = dict(item.get("overrides") or {})
                writer.writerow(
                    {
                        "scenario_id": str(item.get("scenario_id") or ""),
                        "similarity_local_cache_max_size": int(
                            overrides.get(
                                "similarity_local_cache_max_size",
                                LegalResearchTuningConfig().similarity_local_cache_max_size,
                            )
                        ),
                        "semantic_vector_local_cache_max_size": int(
                            overrides.get(
                                "semantic_vector_local_cache_max_size",
                                LegalResearchTuningConfig().semantic_vector_local_cache_max_size,
                            )
                        ),
                        "weike_session_restrict_cooldown_seconds": int(
                            overrides.get(
                                "weike_session_restrict_cooldown_seconds",
                                LegalResearchTuningConfig().weike_session_restrict_cooldown_seconds,
                            )
                        ),
                        "total_cases": int(summary.get("total_cases", 0)),
                        "labeled_cases": int(summary.get("labeled_cases", 0)),
                        "labeled_ratio": float(summary.get("labeled_ratio", 0.0)),
                        "errors": int(summary.get("errors", 0)),
                        "tp": int(summary.get("tp", 0)),
                        "fp": int(summary.get("fp", 0)),
                        "fn": int(summary.get("fn", 0)),
                        "precision": float(summary.get("precision", 0.0)),
                        "recall": float(summary.get("recall", 0.0)),
                        "f1": float(summary.get("f1", 0.0)),
                        "primary_contribution_rate": self._query_type_metric_value(
                            summary=summary,
                            query_type=self.QUERY_TYPE_PRIMARY,
                            key="contribution_rate",
                        ),
                        "expansion_contribution_rate": self._query_type_metric_value(
                            summary=summary,
                            query_type=self.QUERY_TYPE_EXPANSION,
                            key="contribution_rate",
                        ),
                        "feedback_contribution_rate": self._query_type_metric_value(
                            summary=summary,
                            query_type=self.QUERY_TYPE_FEEDBACK,
                            key="contribution_rate",
                        ),
                        "other_contribution_rate": self._query_type_metric_value(
                            summary=summary,
                            query_type=self.QUERY_TYPE_OTHER,
                            key="contribution_rate",
                        ),
                    }
                )
        self.stdout.write(self.style.SUCCESS(f"汇总CSV已写入: {path}"))

    @classmethod
    def _build_ab_scenarios(cls, *, options: dict[str, Any]) -> list[dict[str, Any]]:
        defaults = LegalResearchTuningConfig()
        base_overrides: dict[str, int] = {}
        similarity_single = int(options.get("similarity_local_cache_max_size") or 0)
        semantic_single = int(options.get("semantic_local_cache_max_size") or 0)
        weike_single = int(options.get("weike_session_restrict_cooldown_seconds") or 0)
        if similarity_single > 0:
            base_overrides["similarity_local_cache_max_size"] = similarity_single
        if semantic_single > 0:
            base_overrides["semantic_vector_local_cache_max_size"] = semantic_single
        if weike_single > 0:
            base_overrides["weike_session_restrict_cooldown_seconds"] = weike_single

        ab_similarity = cls._parse_int_list(str(options.get("ab_similarity_local_cache_sizes") or ""))
        ab_semantic = cls._parse_int_list(str(options.get("ab_semantic_local_cache_sizes") or ""))
        ab_weike = cls._parse_int_list(str(options.get("ab_weike_cooldown_seconds") or ""))
        if not any((ab_similarity, ab_semantic, ab_weike)):
            scenario_id = cls._build_scenario_id(overrides=base_overrides)
            return [{"scenario_id": scenario_id, "overrides": base_overrides}]

        similarity_values = ab_similarity or [
            int(base_overrides.get("similarity_local_cache_max_size", defaults.similarity_local_cache_max_size))
        ]
        semantic_values = ab_semantic or [
            int(
                base_overrides.get(
                    "semantic_vector_local_cache_max_size",
                    defaults.semantic_vector_local_cache_max_size,
                )
            )
        ]
        weike_values = ab_weike or [
            int(
                base_overrides.get(
                    "weike_session_restrict_cooldown_seconds",
                    defaults.weike_session_restrict_cooldown_seconds,
                )
            )
        ]

        scenarios: list[dict[str, Any]] = []
        seen: set[str] = set()
        for sim, sem, wk in product(similarity_values, semantic_values, weike_values):
            overrides = dict(base_overrides)
            overrides["similarity_local_cache_max_size"] = int(sim)
            overrides["semantic_vector_local_cache_max_size"] = int(sem)
            overrides["weike_session_restrict_cooldown_seconds"] = int(wk)
            scenario_id = cls._build_scenario_id(overrides=overrides)
            if scenario_id in seen:
                continue
            seen.add(scenario_id)
            scenarios.append({"scenario_id": scenario_id, "overrides": overrides})
        return scenarios

    @staticmethod
    def _parse_int_list(raw: str) -> list[int]:
        values: list[int] = []
        for part in str(raw or "").split(","):
            token = part.strip()
            if not token:
                continue
            try:
                value = int(token)
            except (TypeError, ValueError):
                continue
            if value <= 0:
                continue
            values.append(value)
        # 去重并保持顺序
        seen: set[int] = set()
        ordered: list[int] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered

    @staticmethod
    def _build_scenario_id(*, overrides: dict[str, int]) -> str:
        if not overrides:
            return "default"
        return (
            f"sim{int(overrides.get('similarity_local_cache_max_size', 0))}"
            f"_sem{int(overrides.get('semantic_vector_local_cache_max_size', 0))}"
            f"_wk{int(overrides.get('weike_session_restrict_cooldown_seconds', 0))}"
        )

    @classmethod
    @contextmanager
    def _temporary_tuning_overrides(cls, overrides: dict[str, int]):
        payload = {k: int(v) for k, v in dict(overrides or {}).items() if int(v) > 0}
        if not payload:
            yield
            return

        original = LegalResearchTuningConfig.__dict__.get("load")
        if not isinstance(original, classmethod):
            yield
            return

        def _patched_load(patched_cls: type[LegalResearchTuningConfig]) -> LegalResearchTuningConfig:
            base = original.__get__(None, patched_cls)()
            filtered = {k: v for k, v in payload.items() if hasattr(base, k)}
            if not filtered:
                return base
            return replace(base, **filtered)

        LegalResearchTuningConfig.load = classmethod(_patched_load)
        try:
            yield
        finally:
            LegalResearchTuningConfig.load = original

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
            normalized_item = dict(item)
            normalized_item["query_type"] = cls._normalize_query_type(
                item.get("query_type") or item.get("query_strategy_type")
            )
            normalized.append(normalized_item)
        return normalized

    @staticmethod
    def _write_template(*, path: Path) -> None:
        template = {
            "schema_version": "v2",
            "name": "legal_research_baseline_v1",
            "description": (
                "请替换为你自己的标注样本。expected_relevant_doc_ids 为空时，"
                "该样本仅用于可用性回放，不参与 PRF 统计。"
            ),
            "query_type_notes": {
                "primary": "主查询（核心检索词）",
                "expansion": "扩展查询（同义词/意图扩展）",
                "feedback": "反馈查询（由在线反馈追加）",
                "other": "未归类",
            },
            "cases": [
                {
                    "case_id": "sample-001",
                    "credential_id": 6,
                    "query_type": "primary",
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
                    "notes": "示例样本，请替换为真实标注",
                },
                {
                    "case_id": "sample-002",
                    "credential_id": 6,
                    "query_type": "expansion",
                    "keyword": "借款合同 逾期利息 保证责任",
                    "case_summary": "借款人逾期未还，出借人主张借款本息并要求保证人承担连带责任。",
                    "target_count": 3,
                    "max_candidates": 100,
                    "min_similarity_score": 0.82,
                    "llm_model": "Qwen/Qwen2.5-7B-Instruct",
                    "expected_relevant_doc_ids": [],
                    "notes": "示例样本，请替换为真实标注",
                },
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
