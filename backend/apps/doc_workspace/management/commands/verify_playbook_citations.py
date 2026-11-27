"""核对标准库里的**每一条域外法引用**在 BARLC 里是否真的成立。

## 为什么标准库也要被核验

标准库是审查的「尺子」。尺子上的刻度如果有一格是编的，整份清单的可信度就没了——
而标准库最容易编错的地方恰恰是**条号**：法名好记，条号难记。

这套分册（`services/playbook_asean.py`）里的条号，凡标了 `Section N` 的都在
2026-11-27 用 BARLC 泰国/越南/印尼/柬埔寨/老挝/缅甸库逐条核到过原文；标
`（条号待核）` 的只核到「法存在」。**BARLC 会变**（新法入库、PDF 重切分、法名改译），
所以这条核验要能随时重跑，而不是只信一次性记录。

## 判据（三档，与 `foreign_law.classify_status` 同源）

| 结论 | 含义 | 退出码影响 |
|:--|:--|:--|
| `ok` | 条号核到原文 / 只引法名且法存在 | 无 |
| `pending` | 标了「条号待核」且法存在 —— 已知且已声明 | 无 |
| `missing` | **库里查无此法** —— 标准库引了一部不存在的法 | **退出码 1** |
| `drift` | 标了 `Section N` 但核不到原文（原来是核过的） | 退出码 1 |

用法：

```bash
cd backend/apiSystem
../../backend/.venv/bin/python manage.py verify_playbook_citations                # 全部法域
../../backend/.venv/bin/python manage.py verify_playbook_citations --jurisdiction VN
```
"""

from __future__ import annotations

import re
import sys
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.doc_workspace.services import foreign_law, playbook_asean, playbook_service

#: 从 `legal_basis` 里抠条号：`Section 8` / `Article 21` / `Section 77/1` / `Section 19 bis`
_SECTION_RE = re.compile(r"(?:Section|Article|Sec\.|Art\.)\s*([0-9]+(?:\s*(?:bis|ter|/[0-9]+))?)", re.IGNORECASE)


def _target(rule: dict[str, Any]) -> tuple[str, str]:
    """取核验目标：优先用规则里的机器字段，退化时再从展示串里抠。

    机器字段（`verify_law` / `verify_section`）是权威：展示串里带法号、中文括注、
    「条号待核」，直接拿去检索会零命中——真机因此误报过 19 条「引用了不存在的法」。
    """
    law = str(rule.get("verify_law") or "").strip()
    section = str(rule.get("verify_section") or "").strip().lower()
    if law:
        return law, section
    basis = str(rule.get("legal_basis") or "")
    match = _SECTION_RE.search(basis)
    if match:
        return basis[: match.start()].strip(" ，,;；（("), re.sub(r"\s+", "", match.group(1)).lower()
    return basis.replace(playbook_asean.PENDING, "").strip(), ""


class Command(BaseCommand):
    help = "用 BARLC 核验标准库里每一条域外法引用（法是否存在 / 条号是否真的在）"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--jurisdiction", default="", help="只核某个法域（默认全部有分册的）")
        parser.add_argument("--sleep", type=float, default=1.5, help="每次调用间隔秒数（BARLC 有频率限制）")

    def handle(self, *args: Any, **options: Any) -> None:
        jurisdictions = (
            [options["jurisdiction"].upper()] if options["jurisdiction"] else list(playbook_asean.RULES_BY_JURISDICTION)
        )
        verifier = foreign_law.default_verifier()
        if verifier is None:
            self.stderr.write(self.style.ERROR("域外法查明不可用（插件或凭据缺失），无法核验"))
            sys.exit(2)

        rows: list[tuple[str, str, str, str, str]] = []
        for code in jurisdictions:
            country_code = foreign_law.BARLC_COUNTRY_CODE.get(code, "")
            if not country_code:
                self.stdout.write(self.style.WARNING(f"{code}: 无 BARLC 国别码，跳过"))
                continue
            rules = playbook_asean.RULES_BY_JURISDICTION.get(code, [])
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n== {code}（{len(rules)} 条规则，{country_code}）"))
            for rule in rules:
                law, section = _target(rule)
                if not law or law.startswith("（"):
                    # 引用完整性那三条不是外部法源，无需核验
                    continue
                evidence = verifier(
                    foreign_law.Citation(law_name=law, section_number=section, raw=rule["rule_key"]),
                    country_code=country_code,
                )
                verdict = self._verdict(rule=rule, evidence=evidence)
                rows.append((code, rule["rule_key"], law, section or "-", verdict))
                self.stdout.write(f"  [{verdict}] {rule['rule_key']}: {law} {section or ''} — {evidence.reason[:70]}")
                time.sleep(max(0.0, float(options["sleep"])))

        self._summary(rows)

    @staticmethod
    def _verdict(*, rule: dict[str, Any], evidence: foreign_law.CitationEvidence) -> str:
        declared_pending = playbook_asean.PENDING in str(rule.get("legal_basis") or "")
        if evidence.status == foreign_law.STATUS_MISSING_LAW:
            return "missing"
        if evidence.status == foreign_law.STATUS_VERIFIED:
            return "pending" if declared_pending else "ok"
        if evidence.status == foreign_law.STATUS_UNCONFIRMED:
            # 标了待核 + 只是查不清 = 已知状态；标了 Section 却查不清 = 漂移
            return "pending" if declared_pending else "drift"
        if evidence.status == foreign_law.STATUS_MISSING_SECTION:
            # 法在、条号不在 —— 标了待核算已知；声称「条号已核」就是漂移
            return "pending" if declared_pending else "drift"
        return "unavailable"

    def _summary(self, rows: list[tuple[str, str, str, str, str]]) -> None:
        counts: dict[str, int] = {}
        for *_rest, verdict in rows:
            counts[verdict] = counts.get(verdict, 0) + 1
        self.stdout.write(self.style.MIGRATE_HEADING("\n== 汇总"))
        for key in ("ok", "pending", "drift", "missing", "unavailable"):
            if counts.get(key):
                self.stdout.write(f"  {key}: {counts[key]}")
        broken = counts.get("missing", 0) + counts.get("drift", 0)
        if broken:
            self.stderr.write(self.style.ERROR(f"\n发现 {broken} 条引用的结论与标准库声明不符，请核对后修正"))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("\n全部引用与声明一致"))
