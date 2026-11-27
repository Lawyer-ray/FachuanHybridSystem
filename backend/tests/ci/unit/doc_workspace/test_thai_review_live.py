"""域外法审查**真机**自检：真 BARLC + 真模型，跑一遍泰国合同。

## 为什么这条要单独一个文件、且默认 skip

它依赖两件 CI 里没有的东西：

1. **BARLC 账号**（Django Admin「账号密码」里 site_name=barlc）与公网可达；
2. **真实 LLM 网关**（审查本身要一次模型调用）。

所以默认 `skip`，只有显式置 `FACHUAN_LIVE_BARLC=1` 才跑。**它不是回归测试**——
回归靠 `test_foreign_law.py` / `test_thai_contract_review.py` 那两个用假核验器的用例；
这条是「链路到底通不通、真模型会不会照着原文比对」的现场取证。

跑法：

```bash
cd backend
env -u PYTHONHOME -u PYTHONPATH DB_NAME=test_fachuan_dev FACHUAN_LIVE_BARLC=1 \
  .venv/bin/pytest tests/ci/unit/doc_workspace/test_thai_review_live.py -q -s \\
  --reuse-db --timeout=900
```

`-s` 是必须的：清单和查明摘要会打出来，供人工判断模型抓到几条埋点。
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

import pytest
from docx import Document

from apps.doc_workspace.models import Jurisdiction, Stance
from apps.doc_workspace.services import foreign_law, review_pipeline

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        not os.environ.get("FACHUAN_LIVE_BARLC"),
        reason="真机自检：需要 BARLC 凭据 + 真实模型网关，置 FACHUAN_LIVE_BARLC=1 才跑",
    ),
]

logger = logging.getLogger(__name__)

FIXTURE = Path(__file__).parent / "fixtures" / "thai_land_lease_zh_en.md"


def test_live_thai_review_finds_fabricated_statute() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)

    run = review_pipeline.run_review(
        kind="contract",
        owner_id=8801,
        subpath="1-合同/泰国春武里土地租赁.docx",
        stance=Stance.PARTY_B,
        contract_type="土地租赁",
        jurisdiction=Jurisdiction.TH,
        raw_bytes=buf.getvalue(),
        text=text,
    )

    assert run.status == "done", run.error_message

    # ① 域外法查明真的跑起来了（不是「未接入」）
    summary = run.summary.get("foreign_law") or {}
    assert not summary.get("skipped"), f"查明没跑：{summary.get('skipped')}"
    counts = summary.get("counts") or {}
    logger.info("\n=== 域外法查明摘要 ===")
    for item in summary.get("items") or []:
        logger.info(f"  [{item['status']}] {item['law_name']} 第{item['section_number']}条 -> {item['law_title']}")

    # ② 编造的那部法被判出来了（确定性结论，不依赖模型）
    fabricated = [f for f in run.findings.all() if f.rule_key == "foreign_law.citation_invalid"]
    titles = [f.title for f in fabricated]
    logger.info("\n=== 查无此法的结论 ===")
    for title in titles:
        logger.info("  -", title)
    assert any("商业租赁法" in title for title in titles), f"没抓到编造的法律引用，实际：{titles}"
    assert counts.get(foreign_law.STATUS_MISSING_LAW, 0) >= 1

    # ③ 模型产出的清单（埋点对照，人工看）
    logger.info("\n=== 全部结论 ===")
    for finding in run.findings.all().order_by("ordinal"):
        logger.info(f"  [{finding.severity}/{finding.rule_class}/{finding.rule_key}] {finding.title}")
        if finding.legal_basis:
            logger.info(f"      依据：{finding.legal_basis}")
    logger.info("\n=== 标的画像 ===")
    for line in run.summary.get("subject_profile") or []:
        logger.info("  -", line)
    logger.info("\n=== 关系网 ===")
    for relation in run.summary.get("relations") or []:
        logger.info("  -", relation)
