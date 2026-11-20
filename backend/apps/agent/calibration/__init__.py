"""评审校准：指标 → Stage 门禁 → markdown 报告，三段都是纯函数。

    cd backend && .venv/bin/python -m apps.agent.calibration --dry-run
    cd backend && .venv/bin/python -m apps.agent.calibration --data <path>

## 放在 apps 里的原因

它将来要被 CI 在**无数据库**环境跑，也要被 admin / ``/review`` 的校准面板在 Django 内跑，
所以必须是可 import 的正常包，而不是 ``backend/scripts/`` 那种本地脚本
（该目录在 ``.gitignore`` 里明确不入库）。

## 硬约束：本包不 import 任何 Django

models / settings / ORM 一个都不许碰，连间接的也不行。理由不是洁癖：

* 父包链 ``apps`` → ``apps.agent`` 都是空 ``__init__``，所以
  ``python -m apps.agent.calibration`` 能在没有 ``DJANGO_SETTINGS_MODULE`` 的进程里直接跑；
  一旦这里引入了 Django，这条 CLI 立刻变成"必须先 bootstrap"；
* 该校验有机器证据：``tests/ci/unit/agent/review/test_calibration.py`` 用 ``subprocess``
  起一个剥掉 ``DJANGO_SETTINGS_MODULE`` 的子进程跑 ``--dry-run`` 并断言退出码 0。
  **别把它当成可以放宽的"风格建议"**——放宽它等于把无 DB 环境的能力丢掉。

同样刻意**不** import ``apps.agent.services.review``（A3 判定内核，同 app 下的兄弟包）：
校准只吃它产出的 JSON，换成另一套判定实现时这份代码不用改。
"""

from __future__ import annotations

from .agreement import merge_directions, position_consistency
from .metrics import (
    DEFECT_CLASSES,
    CalibrationDataError,
    CalibrationMetrics,
    CalibrationPayload,
    CalibrationSample,
    JudgmentUnit,
    RecallStat,
    compute_metrics,
    load_payload,
    parse_payload,
)
from .report import render_report
from .stage import (
    KAPPA_FLOOR,
    MIN_FAMILIES,
    RECALL_FLOOR,
    STAGE_LABELS,
    TIE_BAND,
    StageCheck,
    StageDecision,
    decide_stage,
)

__all__ = [
    "DEFECT_CLASSES",
    "KAPPA_FLOOR",
    "MIN_FAMILIES",
    "RECALL_FLOOR",
    "STAGE_LABELS",
    "TIE_BAND",
    "CalibrationDataError",
    "CalibrationMetrics",
    "CalibrationPayload",
    "CalibrationSample",
    "JudgmentUnit",
    "RecallStat",
    "StageCheck",
    "StageDecision",
    "compute_metrics",
    "decide_stage",
    "load_payload",
    "merge_directions",
    "parse_payload",
    "position_consistency",
    "render_report",
]
