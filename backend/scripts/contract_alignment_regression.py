#!/usr/bin/env python
"""20 份合同的条款对齐离线回归（切分 → 三栏 patch 分类 → 三类计数表）。

## 用法

```bash
cd <worktree>/backend
PYTHONPATH=.:apiSystem .venv/bin/python scripts/contract_alignment_regression.py
# 有真实快照时：
PYTHONPATH=.:apiSystem .venv/bin/python scripts/contract_alignment_regression.py --snapshot-dir /path/to/snapshots
```

脚本不连数据库（只 ``django.setup()`` 以便 import 项目模块），不调用 LLM，
同一份输入每次输出相同。

## 数据来源与 synthetic 标注

真实 patch 快照目录（JSON，一份合同一个文件）不存在或为空时，脚本使用
**内置的 20 份合成合同**，并在输出第一行明确标注 ``[synthetic]``。合成样本
只验证分类逻辑（互补/互斥/漏项/待人工），**不能**当作真实合同的统计结论。

快照 JSON 形状：

```json
{
  "contract": "sample-01",
  "subpath": "1-合同/sample-01.docx",
  "text": "第一条 ...\\n...",
  "patches": [
    {"patch_id": "p1", "lane": "pi", "original": "...", "replacement": "..."}
  ],
  "checklist": ["第五条"]
}
```

同一快照内所有 patch 共用顶层 ``subpath``。``checklist`` 里的条款 key 必须与
``clause_split`` 切出来的 key 同拼写
（例如 ``第五条``）；拼不上会按"文本中未找到"记漏项。

## 输出

每份合同一行：切分粒度 + 六类计数；最后一行合计。三类主指标是
``互补 / 互斥 / 漏项``，另列 ``待人工``（法律效果存疑）、``重复``、``未定位``
以免把"没算进三类"的情况藏起来。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
os.environ.setdefault("DB_NAME", "test_adj_a8")
# django.setup() 会打一屏 INFO 注册日志；回归脚本只需要计数表。
logging.disable(logging.INFO)

import django

django.setup()

from apps.contract_review.services.alignment import AlignmentReport, classify_patches, split_clauses
from apps.contract_review.services.write_contracts import WritePatch

#: 计数列（顺序即表头顺序）。
COUNT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("complementary", "互补"),
    ("overlap_diff", "互斥"),
    ("missing", "漏项"),
    ("manual", "待人工"),
    ("duplicate", "重复"),
    ("unlocated", "未定位"),
)

_SUBPATH = "1-合同/synthetic-{index:02d}.docx"
_CLAUSE_ONE = "甲方向乙方采购设备{index}台。"
_CLAUSE_TWO = "甲方应于收到发票后三十日内支付货款。"
_CLAUSE_THREE = "乙方逾期交货的，按日万分之五支付违约金。"
_CLAUSE_FOUR_FIRST = "因本合同产生的争议，提交乙方所在地仲裁委员会仲裁。"
_CLAUSE_FOUR_SECOND = "仲裁裁决为终局裁决。"
_CLAUSE_FIVE = "双方应对本合同内容保密。"


@dataclass(frozen=True)
class ContractSnapshot:
    """一份合同的离线输入。"""

    name: str
    subpath: str
    text: str
    patches: tuple[WritePatch, ...]
    checklist: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotRow:
    name: str
    granularity: str
    counts: dict[str, int]


def _synthetic_text(index: int) -> str:
    return "\n".join(
        [
            f"第{index}号采购合同",
            "第一条 合同标的",
            _CLAUSE_ONE.format(index=index),
            "第二条 付款方式",
            _CLAUSE_TWO,
            "第三条 违约责任",
            _CLAUSE_THREE,
            "第四条 争议解决",
            f"{_CLAUSE_FOUR_FIRST}{_CLAUSE_FOUR_SECOND}",
            "第五条 保密",
            _CLAUSE_FIVE,
        ]
    )


def _patch(snapshot_index: int, suffix: str, lane: str, original: str, replacement: str) -> WritePatch:
    return WritePatch(
        patch_id=f"syn-{snapshot_index:02d}-{suffix}",
        session_id="alignment-regression",
        turn=1,
        agent_kind=lane,
        run_id=f"synthetic:{lane}:{snapshot_index}",
        owner_kind="contract",
        owner_id=snapshot_index,
        subpath=_SUBPATH.format(index=snapshot_index),
        original=original,
        replacement=replacement,
    )


def _synthetic_snapshots() -> list[ContractSnapshot]:
    """20 份确定性合成合同：每份固定出现互补/互斥/漏项，4 的倍数再加待人工。"""

    snapshots: list[ContractSnapshot] = []
    for index in range(1, 21):
        original_one = _CLAUSE_ONE.format(index=index)
        patches = [
            _patch(index, "pi-1", "pi", original_one, f"{original_one[:-1]}（含安装调试）。"),
            _patch(index, "dsh-1", "dsh", _CLAUSE_TWO, "甲方应于收到发票后十五日内支付货款。"),
            _patch(index, "pi-2", "pi", _CLAUSE_THREE, "乙方逾期交货的，按日万分之三支付违约金。"),
            _patch(index, "dsh-2", "dsh", _CLAUSE_THREE, "乙方逾期交货的，按日万分之十支付违约金。"),
        ]
        if index % 4 == 0:
            patches.extend(
                [
                    _patch(
                        index,
                        "pi-3",
                        "pi",
                        _CLAUSE_FOUR_FIRST,
                        "因本合同产生的争议，提交甲方所在地仲裁委员会仲裁。",
                    ),
                    _patch(
                        index,
                        "dsh-3",
                        "dsh",
                        _CLAUSE_FOUR_SECOND,
                        "仲裁裁决不是终局裁决，任何一方均可向法院起诉。",
                    ),
                ]
            )
        snapshots.append(
            ContractSnapshot(
                name=f"synthetic-{index:02d}",
                subpath=_SUBPATH.format(index=index),
                text=_synthetic_text(index),
                patches=tuple(patches),
                checklist=("第五条",),
            )
        )
    return snapshots


def _load_snapshots(directory: Path) -> tuple[list[ContractSnapshot], str]:
    """优先读真实快照；目录不存在/为空时返回 synthetic 并带标注。"""

    files = sorted(directory.glob("*.json")) if directory.is_dir() else []
    if not files:
        reason = f"快照目录不存在：{directory}" if not directory.is_dir() else f"快照目录为空：{directory}"
        return _synthetic_snapshots(), f"synthetic（{reason}；使用内置 20 份合成样本）"

    snapshots = [_snapshot_from_file(path, index) for index, path in enumerate(files, start=1)]
    return snapshots, f"snapshots（{directory}，{len(snapshots)} 份）"


def _snapshot_from_file(path: Path, index: int) -> ContractSnapshot:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"读取快照失败：{path}：{exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"快照必须是 JSON 对象：{path}")

    name = str(raw.get("contract") or path.stem)
    subpath = str(raw.get("subpath") or _SUBPATH.format(index=index))
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"快照缺少非空 text：{path}")

    patches = tuple(
        _patch_from_item(item, path, index, position, subpath)
        for position, item in enumerate(_as_list(raw.get("patches"), path, "patches"))
    )
    checklist = tuple(str(key) for key in _as_list(raw.get("checklist", []), path, "checklist"))
    return ContractSnapshot(name=name, subpath=subpath, text=text, patches=patches, checklist=checklist)


def _patch_from_item(item: Any, path: Path, index: int, position: int, subpath: str) -> WritePatch:
    if not isinstance(item, dict):
        raise ValueError(f"patches[{position}] 必须是对象：{path}")
    original = item.get("original")
    replacement = item.get("replacement")
    if not isinstance(original, str) or not original:
        raise ValueError(f"patches[{position}].original 必须是非空字符串：{path}")
    if not isinstance(replacement, str):
        raise ValueError(f"patches[{position}].replacement 必须是字符串：{path}")
    lane = str(item.get("lane") or "lane")
    return WritePatch(
        patch_id=str(item.get("patch_id") or f"{path.stem}-p{position + 1}"),
        session_id=str(item.get("session_id") or "alignment-regression"),
        turn=int(item.get("turn") or 1),
        agent_kind=str(item.get("agent_kind") or lane),
        run_id=str(item.get("run_id") or f"{path.stem}:{lane}:{position + 1}"),
        owner_kind=str(item.get("owner_kind") or "contract"),  # type: ignore[arg-type]
        owner_id=int(item.get("owner_id") or index),
        subpath=subpath,
        original=original,
        replacement=replacement,
    )


def _as_list(value: Any, path: Path, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} 必须是数组：{path}")
    return value


def _run_snapshot(snapshot: ContractSnapshot) -> tuple[SnapshotRow, AlignmentReport]:
    split = split_clauses(snapshot.text)
    report = classify_patches(
        snapshot.patches,
        {snapshot.subpath: snapshot.text},
        {snapshot.subpath: snapshot.checklist},
    )
    row = SnapshotRow(
        name=snapshot.name,
        granularity=split.granularity,
        counts=report.counts(),
    )
    return row, report


def _format_table(rows: list[SnapshotRow], totals: Counter[str]) -> str:
    header = "| 合同 | 切分 | " + " | ".join(label for _key, label in COUNT_COLUMNS) + " |"
    separator = "|:--|:--|" + "|".join("--:" for _key, _label in COUNT_COLUMNS) + "|"
    lines = [header, separator]
    for row in rows:
        values = " | ".join(str(row.counts.get(key, 0)) for key, _label in COUNT_COLUMNS)
        lines.append(f"| {row.name} | {row.granularity} | {values} |")
    total_values = " | ".join(str(totals.get(key, 0)) for key, _label in COUNT_COLUMNS)
    lines.append(f"| **合计（{len(rows)} 份）** | — | {total_values} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="20 份合同的条款对齐离线回归")
    parser.add_argument(
        "--snapshot-dir",
        default=os.environ.get("CONTRACT_ALIGNMENT_SNAPSHOT_DIR", ""),
        help="真实 patch 快照目录（JSON，一份合同一个文件）；缺省用内置 synthetic 样本",
    )
    args = parser.parse_args(argv)

    if args.snapshot_dir:
        snapshots, source = _load_snapshots(Path(args.snapshot_dir).expanduser())
    else:
        snapshots = _synthetic_snapshots()
        source = "synthetic（未指定快照目录；使用内置 20 份合成样本）"
    rows: list[SnapshotRow] = []
    totals: Counter[str] = Counter()
    reports: list[AlignmentReport] = []
    for snapshot in snapshots:
        row, report = _run_snapshot(snapshot)
        rows.append(row)
        reports.append(report)
        totals.update(row.counts)

    print(f"[数据来源] {source}")
    print(_format_table(rows, totals))
    conflict_count = sum(len(report.conflicts) for report in reports)
    note_count = sum(len(report.notes) for report in reports)
    print(f"[明细] PatchConflict {conflict_count} 条；切分/清单提示 {note_count} 条")
    if source.startswith("synthetic"):
        print("[声明] synthetic 结果只用于验证分类逻辑，不代表真实合同统计。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
