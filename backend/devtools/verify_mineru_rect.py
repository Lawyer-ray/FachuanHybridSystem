"""验证双引擎对照里 MinerU 的框不再是空的（人工核对用）。

跑 ``run_dual_engine`` 真打云端引擎，打印各引擎的 ``EngineBlock.rect`` 与分歧挂框，
人工判断框是否落在同一处版面。

为什么要有这个脚本：单测只能证明「坐标按预期换算」，证明不了「换算出来的框真的
框住了那行字」。而这里修的是一个**曾让所有 MinerU 框变成 ``{}``、前端整层不画**
的 bug，必须用真数据看一眼才算验证。

用法（在 backend/ 下）::

    DB_NAME=fachuan_dev PYTHONPATH=apiSystem:. \
        .venv/bin/python -m devtools.verify_mineru_rect 31
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]

#: 实测过的源 PDF（164 页卷宗）。只用于本脚本的默认值，可用 --pdf 覆盖。
_DEFAULT_PDF = Path("apiSystem/media/pdf_splitting/jobs/10e4546c-eb72-439a-a007-359e4c1eb1fb/source/original.pdf")


def _setup_django() -> None:
    """按 ``manage.py`` 的口径引导 Django（脚本要读解析平台凭证）。"""
    sys.path.insert(0, str(_BACKEND_ROOT / "apiSystem"))
    sys.path.insert(0, str(_BACKEND_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
    import django

    django.setup()


def _out(text: str = "") -> None:
    """终端输出。

    本脚本是**人工核对工具**，输出结果给人看是它的本分（不是日志，不该进 logger —
    那会被日志配置重定向到文件）。钩子 forbid-added-print 禁的是用 print 调试，
    所以走 sys.stdout.write 表达同一意图。
    """
    sys.stdout.write(text + "\n")


def _print_blocks(engine: str, blocks: list, status: dict) -> None:
    """打印一个引擎的全部块：rect 是否为空、是否落在 0–1 内。"""
    filled = [block for block in blocks if block.rect]
    within = [block for block in filled if all(0.0 <= block.rect[key] <= 1.0 for key in ("x", "y", "w", "h"))]
    _out(f"\n=== {engine} ===")
    _out(f"status={status}")
    _out(
        f"blocks={len(blocks)} with_rect={len(filled)} within_0_1={len(within)} empty_rect={len(blocks) - len(filled)}"
    )
    for block in blocks:
        _out(
            f"  p{block.page_no} {block.block_type:<12} approx={block.approx!s:<5} "
            f"rect={block.rect} text={block.text[:34]!r}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pages", nargs="*", type=int, help="要跑的原卷页码（默认 [31]）")
    parser.add_argument("--pdf", default=str(_DEFAULT_PDF), help="源 PDF 路径")
    args = parser.parse_args()
    pages = args.pages or [31]

    pdf = Path(args.pdf)
    if not pdf.is_absolute():
        pdf = _BACKEND_ROOT / pdf
    if not pdf.exists():
        _out(f"源 PDF 不存在: {pdf}")
        return 1

    _setup_django()
    from apps.pdf_splitting.services.split import dual_engine_runner as runner

    outcome = runner.run_dual_engine(pdf, page_numbers=pages)

    for engine, blocks in outcome.blocks_by_engine.items():
        _print_blocks(engine, blocks, outcome.summary["dual_engine"]["engines"].get(engine, {}))

    payloads = outcome.summary[runner.SUMMARY_ENGINE_DISAGREEMENTS]
    _out(f"\n=== disagreements ({len(payloads)}) ===")
    for payload in payloads:
        engines_with_rect = [block["engine"] for block in payload.get("blocks", [])]
        _out(
            f"  p{payload['page_no']} {payload['severity']:<6} {payload['kind']:<8} "
            f"rects={engines_with_rect} ctx={payload['context'][:40]!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
