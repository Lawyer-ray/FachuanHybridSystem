"""命令行入口：读数据 → 算指标 → 判 Stage → 出报告，一次跑完整条链路。

    cd backend && .venv/bin/python -m apps.agent.calibration --dry-run
    cd backend && .venv/bin/python -m apps.agent.calibration --data <path>

不需要 ``DJANGO_SETTINGS_MODULE``、不需要 PYTHONPATH：从 ``backend/`` 目录跑，``-m``
会把当前目录放进 ``sys.path``，而本包（及其父包 ``apps``/``apps.agent``）都不碰 Django。

两种模式的区别只有"数据从哪来"：

* ``--dry-run``：内置合成样本。它存在的唯一目的是让报告每一节都有非空值可看
  （含两条因换序不一致被剔除的单元、一条漏改 FN、一条越界 FP、以及一个没标注的
  子类），**它的数字不是校准结论**，报告首行会写明来源是合成样本。
* ``--data <path>``：真实校准数据，形状见 ``metrics.py`` 模块 docstring。
  **本批不提供真实数据**：文件不给、schema 不合规都直接报错退出（码 2），
  绝不回退到合成样本——静默回退会把"没跑过"显示成"跑过了"，是最难发现的那类假绿。
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .metrics import CalibrationDataError, compute_metrics, load_payload, parse_payload
from .report import render_report
from .stage import decide_stage

#: ``--dry-run`` 用的合成样本。刻意覆盖四种情况：一致、换序打架（tie）、
#: 越界误纳（FP）、引用失效漏判（FN），外加一个"这批没标注"的子类（越界 recall = 没数据）。
#: 合同号是虚构的，不含任何真实客户信息。
_SYNTHETIC_RAW: dict[str, Any] = {
    "rubric_id": "contract_answer_v1",
    "rubric_version": "synthetic",
    "families_agreeing": 2,
    "margin": 0.18,
    "samples": [
        {
            "contract_id": "C-SYN-001",
            "items": [
                {
                    "rubric_id": "miss_risk_identified",
                    "defect_class": "miss",
                    "lawyer_defect": True,
                    "judge_defect_forward": True,
                    "judge_defect_reverse": True,
                },
                {
                    "rubric_id": "miss_clause_located",
                    "defect_class": "miss",
                    "lawyer_defect": True,
                    "judge_defect_forward": True,
                    "judge_defect_reverse": True,
                },
                {
                    "rubric_id": "miss_consequence",
                    "defect_class": "miss",
                    "lawyer_defect": True,
                    "judge_defect_forward": True,
                    "judge_defect_reverse": False,
                },
                {
                    "rubric_id": "over_scope",
                    "defect_class": "over",
                    "lawyer_defect": False,
                    "judge_defect_forward": False,
                    "judge_defect_reverse": False,
                },
                {
                    "rubric_id": "over_unrequested_rewrite",
                    "defect_class": "over",
                    "lawyer_defect": False,
                    "judge_defect_forward": False,
                    "judge_defect_reverse": False,
                },
                {
                    "rubric_id": "cite_exists",
                    "defect_class": "cite",
                    "lawyer_defect": False,
                    "judge_defect_forward": False,
                    "judge_defect_reverse": False,
                },
                {
                    "rubric_id": "cite_in_force",
                    "defect_class": "cite",
                    "lawyer_defect": False,
                    "judge_defect_forward": False,
                    "judge_defect_reverse": False,
                },
            ],
        },
        {
            "contract_id": "C-SYN-002",
            "items": [
                {
                    "rubric_id": "miss_risk_identified",
                    "defect_class": "miss",
                    "lawyer_defect": True,
                    "judge_defect_forward": True,
                    "judge_defect_reverse": True,
                },
                {
                    "rubric_id": "miss_clause_located",
                    "defect_class": "miss",
                    "lawyer_defect": True,
                    "judge_defect_forward": False,
                    "judge_defect_reverse": True,
                },
                {
                    "rubric_id": "miss_consequence",
                    "defect_class": "miss",
                    "lawyer_defect": False,
                    "judge_defect_forward": False,
                    "judge_defect_reverse": False,
                },
                {
                    "rubric_id": "over_scope",
                    "defect_class": "over",
                    "lawyer_defect": False,
                    "judge_defect_forward": False,
                    "judge_defect_reverse": False,
                },
                {
                    "rubric_id": "over_unrequested_rewrite",
                    "defect_class": "over",
                    "lawyer_defect": False,
                    "judge_defect_forward": True,
                    "judge_defect_reverse": True,
                },
                {
                    "rubric_id": "cite_exists",
                    "defect_class": "cite",
                    "lawyer_defect": True,
                    "judge_defect_forward": False,
                    "judge_defect_reverse": False,
                },
                {
                    "rubric_id": "cite_in_force",
                    "defect_class": "cite",
                    "lawyer_defect": False,
                    "judge_defect_forward": False,
                    "judge_defect_reverse": False,
                },
            ],
        },
    ],
}


#: 本 CLI 自己的 logger 名（不用 root：Django 的 LOGGING 会接管 root 并改写格式）。
_LOGGER_NAME = "apps.agent.calibration"


def main(argv: Sequence[str] | None = None) -> int:
    """跑一次校准；返回进程退出码（0 成功，2 数据不可用）。"""
    args = _build_parser().parse_args(argv)
    logger = _build_logger()
    if args.dry_run:
        payload = parse_payload(_SYNTHETIC_RAW, source="<dry-run 合成样本>")
        provenance = "内置合成样本（--dry-run 冒烟，数字不是校准结论，勿引用）"
    else:
        try:
            payload = load_payload(args.data)
        except CalibrationDataError as exc:
            logger.error("error: %s", exc)
            return 2
        provenance = f"真实校准数据：{args.data}"

    metrics = compute_metrics(payload)
    decision = decide_stage(
        metrics.kappa,
        metrics.recall_for("miss"),
        metrics.recall_for("cite"),
        payload.families_agreeing,
        payload.margin,
    )
    logger.info(
        render_report(
            provenance=provenance,
            rubric_id=payload.rubric_id,
            rubric_version=payload.rubric_version,
            metrics=metrics,
            decision=decision,
        )
    )
    return 0


def _build_logger() -> logging.Logger:
    """把报告发到 stdout、错误发到 stderr。

    为什么不用 ``print``：仓库的 pre-commit 守卫禁止应用代码 print（那里的 print 是
    "忘了写日志"的代名词，会污染服务端 stdout）。但这里的 stdout **就是产物本身**，
    所以显式挂 handler 且格式只留 ``%(message)s``，避免 "INFO:" 前缀污染报告正文。

    handler 每次调用都重建：``capsys`` / ``contextlib.redirect_stdout`` 会替换
    ``sys.stdout``，缓存的 handler 会继续绑在旧流上，导致测试与重定向都抓不到输出。
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter("%(message)s"))
    # 错误只走 stderr：stdout 必须是纯报告，否则 ``--data`` 失败时会多出一段半截产物。
    stdout_handler.addFilter(lambda record: record.levelno < logging.ERROR)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter("%(message)s"))
    stderr_handler.setLevel(logging.ERROR)
    logger.addHandler(stdout_handler)
    logger.addHandler(stderr_handler)
    return logger


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m apps.agent.calibration",
        description="评审校准骨架：算指标、判 Stage、出 markdown 报告。",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="用内置合成样本跑通全链路（数字不是校准结论）")
    group.add_argument("--data", type=Path, metavar="PATH", help="真实校准数据 JSON 路径（本批不提供）")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
