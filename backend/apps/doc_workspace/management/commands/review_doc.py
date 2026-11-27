"""拿一份**本地文件**跑一遍文档工作面审查（域外法查明 + 标准库 + 模型），打印清单。

## 为什么需要这个命令

审查链的正规入口是「文件夹里的文件 + MCP/REST」，它需要一份已经落进绑定文件夹、
且属于某个合同/案件的 docx。要做「这条链路到底通不通」的现场取证时，为了跑一次就得
先造合同、造案件、造文件夹、传文件——成本远高于收益，于是这条链路长期只有单测覆盖，
真机（真 BARLC + 真模型）一年也没人跑过。

本命令把「本地文件」直接当输入，审查结果默认**整体回滚**（不污染工作库）：

```bash
cd backend/apiSystem
../../backend/.venv/bin/python manage.py review_doc \
  --file ../tests/ci/unit/doc_workspace/fixtures/thai_land_lease_zh_en.md \
  --jurisdiction TH --contract-type 土地租赁 --stance party_b
```

默认打印：域外法查明摘要（每条引用的结论）、每一条结论、标的画像与关系网。
`--keep` 才会把 ReviewRun/Finding 真正写进库（用于在前端右栏复现）。

## 它不是测试的替代品

回归靠 `tests/ci/unit/doc_workspace/test_foreign_law.py` 与 `test_thai_contract_review.py`
（假核验器，秒级）。本命令是**真机取证**工具：需要 BARLC 凭据与可用的 LLM 后端，
所以它不进 CI，也不假装是护栏。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.doc_workspace.models import Jurisdiction, ReviewRun, Stance
from apps.doc_workspace.services import foreign_law, playbook_service, review_pipeline


class Command(BaseCommand):
    help = "用本地文件跑一遍文档工作面审查（默认回滚，不写库）"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--file", required=True, help="输入文件（.docx / .md / .txt）")
        parser.add_argument("--jurisdiction", default=Jurisdiction.CN, help="审查法域（CN/TH/VN/…）")
        parser.add_argument("--contract-type", default="", help="合同类型（决定用哪套标准库）")
        parser.add_argument("--stance", default=Stance.NEUTRAL, help="立场：party_a / party_b / neutral")
        parser.add_argument("--kind", default="contract", help="owner 类型：contract / case")
        parser.add_argument("--owner-id", type=int, default=0, help="所属合同/案件 ID（默认 0，仅用于坐标）")
        parser.add_argument("--subpath", default="", help="文件夹内相对路径（默认用文件名）")
        parser.add_argument(
            "--no-foreign-law",
            action="store_true",
            help="跳过域外法查明（离线排障时用；跳过会写进 summary 的 skipped 原因）",
        )
        parser.add_argument("--keep", action="store_true", help="保留审查结果（默认整体回滚）")

    def handle(self, *args: Any, **options: Any) -> None:
        path = Path(options["file"]).expanduser().resolve()
        if not path.exists():
            self.stderr.write(self.style.ERROR(f"文件不存在：{path}"))
            return

        jurisdiction = playbook_service.normalise_jurisdiction(options["jurisdiction"])
        text, raw_bytes = _load(path)
        subpath = options["subpath"] or path.name

        self.stdout.write(
            f"审查 {path.name} | 法域 {jurisdiction} | 类型 {options['contract_type'] or '通用'} | "
            f"立场 {options['stance']} | {len(text)} 字"
        )
        if options["no_foreign_law"]:
            foreign_law.register_verifier(lambda citation, *, country_code: _skipped(citation))
        try:
            run = review_pipeline.run_review(
                kind=options["kind"],
                owner_id=options["owner_id"],
                subpath=subpath,
                stance=options["stance"],
                contract_type=options["contract_type"],
                jurisdiction=jurisdiction,
                raw_bytes=raw_bytes,
                text=text,
            )
            self._report(run)
            if not options["keep"]:
                # **不用整体事务回滚来「不落库」**：审查里有一次几十秒的模型调用 +
                # 域外法查明，整个进程开着事务干等就是「idle in transaction」，
                # PG 的 `idle_in_transaction_session_timeout` 一到就把连接掐掉
                # （实测症状：保存结论时报 `the connection is closed`）。
                # 改为事后补偿删除：轮次级联删结论，副作用范围与事务回滚一致。
                ReviewRun.objects.filter(id=run.id).delete()
                self.stdout.write(self.style.WARNING("\n（结果已删除，未留在库里；加 --keep 保留）"))
            else:
                self.stdout.write(self.style.SUCCESS(f"\n已保留：run_id={run.id}"))
        finally:
            if options["no_foreign_law"]:
                foreign_law.register_verifier(None)

    def _report(self, run: Any) -> None:
        summary = run.summary or {}
        foreign = summary.get("foreign_law") or {}
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== 域外法查明 ==="))
        if foreign.get("skipped"):
            self.stdout.write(f"  未执行：{foreign['skipped']}")
        if foreign.get("timeout"):
            self.stdout.write("  ⚠ 超时（本轮没有域外法依据）")
        if foreign.get("error"):
            self.stdout.write(f"  ⚠ 失败：{foreign['error']}")
        for item in foreign.get("items") or []:
            self.stdout.write(
                f"  [{item.get('status')}] {item.get('law_name')} 第{item.get('section_number') or '-'}条 "
                f"-> {item.get('law_title') or '（未定位）'} {item.get('reason') or ''}"
            )

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== 结论清单 ==="))
        findings = list(run.findings.all().order_by("ordinal"))
        if not findings:
            self.stdout.write("  （无结论）")
        for finding in findings:
            self.stdout.write(f"  [{finding.severity}/{finding.rule_class}/{finding.rule_key}] {finding.title}")
            if finding.legal_basis:
                self.stdout.write(f"      依据：{finding.legal_basis}")
            if finding.quote:
                self.stdout.write(f"      原文：{finding.quote[:80]}")

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== 标的画像 ==="))
        for line in summary.get("subject_profile") or []:
            self.stdout.write(f"  - {line}")
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== 关系网 ==="))
        for relation in summary.get("relations") or []:
            self.stdout.write(f"  - {relation}")
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== 闸门 ==="))
        self.stdout.write(f"  {summary.get('gates')}")


def _skipped(citation: Any) -> Any:
    return foreign_law.CitationEvidence(citation=citation, status=foreign_law.STATUS_SKIPPED, reason="--no-foreign-law")


def _load(path: Path) -> tuple[str, bytes]:
    """读入文件 → (纯文本, docx 字节)。markdown/txt 现场包成 docx，免得为了取证先造一份 docx。"""
    if path.suffix.lower() == ".docx":
        raw = path.read_bytes()
        from io import BytesIO

        from docx import Document

        from apps.doc_workspace.services.docx.text import full_text

        return full_text(Document(BytesIO(raw))), raw

    text = path.read_text(encoding="utf-8")
    from docx import Document

    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return text, buf.getvalue()
