"""真正**同时**发起的两次写盘：必须只有一次落地。

前面的用例（`test_patch_flow.py`）证明的是"同一份 docx 上有交叠 patch 时拒绝写"——
那是**串行**语义。但多栏并答时最危险的不是串行，而是**两个裁决几乎同时提交**：
两个请求各自读到同一个 `base_mtime`、各自通过校验、然后前后脚 `save()`——
后写的把先写的整份覆盖（文件级 last-write-wins）。这就是"丢更新"。

本用例用两线程 + Barrier 制造真实竞争窗口，钉住三条：

1. 恰好一次成功、另一次必须被拒（409 类冲突），不能两次都 200；
2. 文件里的修订痕迹只有一处改动（没被整体覆盖，也没有两份叠加）；
3. 失败那条 patch 不会停在"已应用"状态（状态与磁盘一致）。

两个 patch 选**互不交叠**的条款，是为了不让"互补冲突检测"提前把其中一条挡掉——
要考的纯粹是 mtime 乐观锁在并发下有没有真的锁住。
"""

from __future__ import annotations

import threading
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from django.db import connection
from docx import Document

from apps.contract_review.services.patch.models import ContractWritePatch, PatchStatus
from apps.contract_review.services.patch.service import apply_patches, collect_patch, docx_full_text
from apps.core.exceptions import ConflictError, ValidationException
from tests.ci.unit.contract_review.services.patch.docx_fixtures import CLAUSE_COURT, CLAUSE_PAYMENT, SUBPATH

PAYMENT_NEW = "甲方应于十五日内支付货款。"
COURT_NEW = "因本合同产生的争议，由甲方所在地人民法院管辖。"


def _collect(contract: Any, original: str, replacement: str, base_mtime: float) -> str:
    # 生产路径（API / MCP）都会带 base_mtime——它就是乐观锁要比对的那个值。
    # 不带的话应用侧会打印「跳过乐观锁二次校验」并直接写盘（真机日志里见过）。
    patch = collect_patch(
        owner_kind="contract",
        owner_id=contract.id,
        subpath=SUBPATH,
        original=original,
        replacement=replacement,
        base_mtime=base_mtime,
    )
    return patch.patch_id


def _doc_text(file_path: Path) -> str:
    return docx_full_text(Document(BytesIO(file_path.read_bytes())))


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_applies_on_same_docx_only_one_wins(bound: Any) -> None:
    lawyer, contract, file_path = bound()
    base_mtime = file_path.stat().st_mtime
    payment_patch = _collect(contract, CLAUSE_PAYMENT, PAYMENT_NEW, base_mtime)
    court_patch = _collect(contract, CLAUSE_COURT, COURT_NEW, base_mtime)

    barrier = threading.Barrier(2)
    outcomes: dict[str, str] = {}

    def _apply(name: str, patch_id: str) -> None:
        try:
            barrier.wait(timeout=10)
            apply_patches(patch_ids=[patch_id], note=f"并发-{name}", user=lawyer)
            outcomes[name] = "ok"
        except ConflictError as exc:  # 期望：后到的那次
            outcomes[name] = f"conflict:{exc.to_dict().get('code')}"
        except (ValidationException, OSError, RuntimeError, ValueError) as exc:
            # 不写 `except Exception`（全仓 ratchet 不许增长）；这几类足够覆盖
            # 并发下的真实失败面，其它异常会直接冒泡，由 pytest 显示原始栈。
            outcomes[name] = f"error:{type(exc).__name__}:{exc}"
        finally:
            # 线程里开的连接必须自己关：否则 pytest teardown 会报「数据库还被 2 个会话占用」
            connection.close()

    threads = [
        threading.Thread(target=_apply, args=("payment", payment_patch)),
        threading.Thread(target=_apply, args=("court", court_patch)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    successes = [name for name, result in outcomes.items() if result == "ok"]
    failures = [result for result in outcomes.values() if result != "ok"]

    assert len(successes) == 1, f"必须恰好一次落地，实际 {outcomes}"
    assert len(failures) == 1 and failures[0].startswith("conflict"), f"另一次要被拒，实际 {outcomes}"

    # 磁盘与状态一致：只有赢家那一条是 applied，另一条不能假装成功
    applied = list(ContractWritePatch.objects.filter(patch_id__in=[payment_patch, court_patch], status=PatchStatus.APPLIED))
    assert len(applied) == 1, [patch.patch_id for patch in applied]

    # 修订痕迹只有一处改动：没被整份覆盖，也没叠两份
    text = _doc_text(file_path)
    changed = sum([PAYMENT_NEW in text, COURT_NEW in text])
    assert changed == 1, f"文件里应只有一处新文本，实际 {changed}（丢了或被覆盖？）"
