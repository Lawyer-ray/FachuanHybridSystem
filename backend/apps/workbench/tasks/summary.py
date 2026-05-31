"""汇总报告生成和 ZIP 打包"""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile

from ..models import BatchJob, BatchJobItem, BatchJobStatus
from .parsing import parse_llm_result

logger = logging.getLogger(__name__)

# ─── 汇总报告 ────────────────────────────────────────────────────────────────

async def generate_summary(
    job_id: UUID,
    prompt: str,
    completed_items: list[BatchJobItem],
) -> str:
    """从每个案例的分析结果中提取元数据，生成 CSV 文件并返回统计摘要。"""
    csv_rows: list[dict[str, str]] = []
    missing_count = 0

    for item in completed_items:
        if not item.result:
            continue

        parsed = parse_llm_result(item.result, item.file_name)

        if parsed["parse_method"] == "regex" and parsed["case_number"] == "未注明" and parsed["conclusion"] == "未注明":
            missing_count += 1
            csv_rows.append(
                {
                    "文件名": item.file_name,
                    "案号": "",
                    "案由": "",
                    "审理法院": "",
                    "法官": "",
                    "书记员": "",
                    "与研究问题相关": "",
                    "结论": "未提取到元数据",
                    "详细分析": "",
                }
            )
            continue

        csv_rows.append(
            {
                "文件名": item.file_name,
                "案号": parsed["case_number"],
                "案由": parsed["cause"],
                "审理法院": parsed["court"],
                "法官": parsed["judge"],
                "书记员": parsed["clerk"],
                "与研究问题相关": "是" if parsed["is_relevant"] else "否",
                "结论": parsed["conclusion"],
                "详细分析": parsed["analysis"],
            }
        )

    if not csv_rows:
        return "所有案例分析结果为空，无法生成汇总。"

    # 生成 CSV
    output = io.StringIO()
    fieldnames = ["文件名", "案号", "案由", "审理法院", "法官", "书记员", "与研究问题相关", "结论", "详细分析"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(csv_rows)
    csv_content = output.getvalue()

    # 写入文件
    csv_filename = f"案例分析汇总_{job_id.hex[:8]}.csv"
    csv_file = ContentFile(csv_content.encode("utf-8-sig"), name=csv_filename)

    def _save_summary() -> None:
        job = BatchJob.objects.get(id=job_id)
        job.summary_file.save(csv_filename, csv_file, save=True)

    await sync_to_async(_save_summary)()

    # 统计
    total = len(csv_rows)
    relevant = sum(1 for r in csv_rows if r.get("与研究问题相关") == "是")
    irrelevant = sum(1 for r in csv_rows if r.get("与研究问题相关") == "否")

    summary_text = (
        f"## 案例分析汇总\n\n"
        f"- 分析要求：{prompt}\n"
        f"- 案例总数：{total}\n"
        f"- 相关案例：{relevant}\n"
        f"- 无关案例：{irrelevant}\n"
    )
    if missing_count:
        summary_text += f"- 未提取到元数据：{missing_count}\n"

    summary_text += "\n汇总表已生成为 CSV 文件，可点击下载。\n"

    if missing_count:
        summary_text += f"\n> 注意：有 {missing_count} 个案例未提取到元数据，可能是分析结果格式不符合预期。\n"

    return summary_text

# ─── ZIP 打包 ────────────────────────────────────────────────────────────────

def build_detail_zip_sync(job_id: UUID) -> bool:
    """同步生成分析详情 ZIP 并保存到 job.detail_zip_file。

    如果没有已完成的项目则返回 False。
    """
    completed_items = list(BatchJobItem.objects.filter(job_id=job_id, status=BatchJobStatus.COMPLETED))
    if not completed_items:
        return False

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        seen_names: dict[str, int] = {}

        for item in completed_items:
            if not item.result:
                continue

            parsed = parse_llm_result(item.result, item.file_name)

            md_parts: list[str] = []
            md_parts.append("# 案例分析报告\n")
            md_parts.append("## 基本信息\n")
            md_parts.append(f"- **文件名**：{item.file_name}")
            md_parts.append(f"- **案号**：{parsed['case_number']}")
            md_parts.append(f"- **案由**：{parsed['cause']}")
            md_parts.append(f"- **审理法院**：{parsed['court']}")
            md_parts.append(f"- **法官**：{parsed['judge']}")
            md_parts.append(f"- **书记员**：{parsed['clerk']}")
            md_parts.append(f"- **与研究问题相关**：{'是' if parsed['is_relevant'] else '否'}")
            md_parts.append("")
            md_parts.append("## 结论\n")
            md_parts.append(parsed["conclusion"])
            md_parts.append("")
            md_parts.append("## 详细分析\n")
            md_parts.append(parsed["analysis"])

            md_content = "\n".join(md_parts)

            # 从原始文件名派生 md 文件名
            base_name = item.file_name
            if "." in base_name:
                base_name = base_name.rsplit(".", 1)[0]
            base_name = re.sub(r"[^0-9A-Za-z一-鿿._-]+", "_", base_name)
            base_name = re.sub(r"_+", "_", base_name).strip("_") or "unnamed"

            md_filename = f"{base_name}.md"

            # 处理重名
            if md_filename in seen_names:
                seen_names[md_filename] += 1
                md_filename = f"{base_name}_{seen_names[md_filename]}.md"
            else:
                seen_names[md_filename] = 0

            zf.writestr(md_filename, md_content.encode("utf-8"))

    zip_buffer.seek(0)
    hex_str = job_id.hex if isinstance(job_id, UUID) else UUID(str(job_id)).hex
    zip_filename = f"案例分析详情_{hex_str[:8]}.zip"
    zip_file = ContentFile(zip_buffer.getvalue(), name=zip_filename)

    job = BatchJob.objects.get(id=job_id)
    job.detail_zip_file.save(zip_filename, zip_file, save=True)
    return True

async def generate_detail_zip(
    job_id: UUID,
    completed_items: list[BatchJobItem],
) -> None:
    """为每个已完成的案例生成独立的 .md 文件，打包为 ZIP。"""
    await sync_to_async(build_detail_zip_sync)(job_id)
