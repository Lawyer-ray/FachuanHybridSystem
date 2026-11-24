"""扫描件归档端到端：真实 HTTP 端点 → 服务端切片 → 命名/版本对齐 → 落进案卷目录。

## 为什么要有这个测试

命名、版本对齐、副本识别被各自的单测覆盖了，但「整条链能不能真的把文件写到
律师的案卷目录里」只有端到端能回答——中间任何一环（路由挂载、权限、job 属主、
storage 路径、切片页区间、落盘目录定位）错了，单测全绿也没用。

## 两种模式

- 默认：**合成用例**（自建案卷目录 + 自造 PDF），CI 里确定性运行。
- 真实材料回放：设 `E2E_CASE_DIR`（案卷目录，会被复制到 tmp 里再跑）+ `E2E_SCAN_PDF`
  （扫描件路径），用真案件目录与真 40 页扫描件跑同一套断言。案卷目录必须先复制，
  **绝不能指向律师的真实案卷**。
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import fitz
import pytest

from apps.cases.models import CaseFolderBinding
from apps.cases.services.material.scan_archive_naming import DUPLICATE_SUBDIR, parse_document_name
from apps.testing.factories import CaseFactory

pytestmark = pytest.mark.django_db

logger = logging.getLogger(__name__)

CASE_NAME = "张某诉某公司买卖合同纠纷一案"
DATE = "20261106"
LITIGATION_SUBDIRS = ["1-起诉状", "4-证据目录", "6-送达地址确认书"]
ENDPOINT = "/api/v1/pdf-splitting/jobs"


# ── 造样例 ──────────────────────────────────────────────────────────────────


def _make_pdf(path: Path, pages: list[str]) -> None:
    """按给定文本逐页生成 PDF（同文本 → 同渲染 → 同页指纹）。

    文本用 ASCII：内置字体没有中文字形，写中文只会渲染成一排点，页与页之间就没差异了。
    """
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((60, 72), text, fontsize=14)
        for line in range(18):
            page.insert_text((60, 110 + line * 36), f"{text[:6]} 第{line + 1}行 正文内容", fontsize=11)
    doc.save(path)
    doc.close()


def _synthetic_case_tree(root: Path) -> Path:
    """案卷目录：`3-一审/1-立案材料/{子目录}`，起诉状里预置一份 V4 草稿。"""
    material = root / "3-一审" / "1-立案材料"
    material.mkdir(parents=True)
    for name in LITIGATION_SUBDIRS:
        (material / name).mkdir()
    (material / "1-起诉状" / f"1-传统起诉状（{CASE_NAME}）V4_20260924.docx").write_bytes(b"draft")
    return material


def _synthetic_scan(path: Path) -> tuple[list[dict[str, object]], dict[str, str]]:
    """3 份起诉状（每份 2 页）+ 证据清单 + 送达地址确认书，共 8 页。"""
    complaint = ["COMPLAINT page one", "COMPLAINT page two"]
    evidence = ["EVIDENCE LIST"]
    address = ["SERVICE ADDRESS"]
    pages = complaint * 3 + evidence + address
    _make_pdf(path, pages)
    segments: list[dict[str, object]] = [
        {"page_start": 1, "page_end": 2, "doc_type": "传统起诉状", "material_type": "complaint"},
        {"page_start": 3, "page_end": 4, "doc_type": "传统起诉状", "material_type": "complaint"},
        {"page_start": 5, "page_end": 6, "doc_type": "传统起诉状", "material_type": "complaint"},
        {"page_start": 7, "page_end": 7, "doc_type": "证据清单", "material_type": "evidence_list"},
        {
            "page_start": 8,
            "page_end": 8,
            "doc_type": "送达地址确认书",
            "material_type": "delivery_address_confirmation",
        },
    ]
    # 起诉状沿用既有草稿的「版本 + 版本日期」（V4_20260924），不是本次归档日期
    expect = {
        "primary": f"1-传统起诉状（{CASE_NAME}）V4_20260924.pdf",
        "copy2": f"1-传统起诉状（{CASE_NAME}）V4_20260924（第2份）.pdf",
        "copy3": f"1-传统起诉状（{CASE_NAME}）V4_20260924（第3份）.pdf",
        "evidence": f"1-证据清单（{CASE_NAME}）V1_{DATE}.pdf",
        "address": f"1-送达地址确认书（{CASE_NAME}）V1_{DATE}.pdf",
    }
    return segments, expect


# ── 走真实 HTTP 端点 ────────────────────────────────────────────────────────


def _create_job(client, pdf_path: Path) -> str:
    payload = {
        "split_mode": "manual_split",  # 不做内容分析：本测试只验证「切片+归档」
        "template_key": "filing_materials_v1",
        "ocr_profile": "fast",
    }
    with pdf_path.open("rb") as handle:
        # 不传 content_type：交给 Django test client 自己生成带 boundary 的 multipart
        response = client.post(ENDPOINT, data={"file": handle, **payload})
    assert response.status_code in (200, 201), response.content[:800]
    return str(response.json()["job_id"])


def _archive(client, job_id: str, case_id: int, segments: list[dict[str, object]], **extra):
    body = {"case_id": case_id, "segments": segments, "date": DATE, "write_duplicates": True, **extra}
    return client.post(
        f"{ENDPOINT}/{job_id}/archive-to-case-folder",
        data=body,
        content_type="application/json",
    )


def _same_rendered_page(pdf: Path, source: Path, page_no: int) -> bool:
    """归档件第 1 页与源 PDF 指定页是否同一页（渲染后逐块墨占比比较）。"""

    def sig(page) -> list[float]:
        pix = page.get_pixmap(dpi=100, colorspace=fitz.csGRAY, alpha=False)
        w, h, s = pix.width, pix.height, pix.samples
        lo, hi = min(s), max(s)
        thr = lo + 0.5 * (hi - lo)
        mask = s.translate(bytes(1 if v <= thr else 0 for v in range(256)))
        out = []
        for by in range(h // 8):
            base = by * 8 * w
            for bx in range(w // 8):
                left = base + bx * 8
                ink = sum(sum(mask[left + l * w : left + l * w + 8]) for l in range(8))
                out.append(ink / 64.0)
        return out

    with fitz.open(pdf) as a, fitz.open(source) as b:
        one, two = sig(a[0]), sig(b[page_no])
    return sum(abs(x - y) for x, y in zip(one, two)) / len(one) <= 0.03


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and not p.name.startswith("."))


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_archive_end_to_end_synthetic(authenticated_client, tmp_path):
    """合成用例：一次归档写正本 + 副本 + 核对说明，重跑不覆盖。"""
    material = _synthetic_case_tree(tmp_path / "case")
    case = CaseFactory(name=CASE_NAME)
    CaseFolderBinding.objects.create(case=case, folder_path=str(tmp_path / "case"))

    scan = tmp_path / "scan.pdf"
    segments, expect = _synthetic_scan(scan)
    job_id = _create_job(authenticated_client, scan)

    response = _archive(authenticated_client, job_id, case.id, segments)
    assert response.status_code == 200, response.content[:800]
    payload = response.json()

    complaint_dir = material / "1-起诉状"
    assert (complaint_dir / expect["primary"]).is_file()
    assert (complaint_dir / DUPLICATE_SUBDIR / expect["copy2"]).is_file()
    assert (complaint_dir / DUPLICATE_SUBDIR / expect["copy3"]).is_file()
    assert (material / "4-证据目录" / expect["evidence"]).is_file()
    assert (material / "6-送达地址确认书" / expect["address"]).is_file()
    # 草稿一个字节都不能动
    assert (complaint_dir / f"1-传统起诉状（{CASE_NAME}）V4_20260924.docx").read_bytes() == b"draft"

    # 正本是 2 页；切片没有串页（与源 PDF 第 1 页渲染一致）
    with fitz.open(complaint_dir / expect["primary"]) as doc:
        assert doc.page_count == 2
    assert _same_rendered_page(complaint_dir / expect["primary"], scan, 0)

    names = {item["filename"] for item in payload["written"]}
    assert expect["primary"] in names and expect["evidence"] in names
    assert len(payload["duplicates"]) == 1 and len(payload["duplicates"][0]) == 3
    assert payload["notice_path"] and Path(payload["notice_path"]).is_file()
    notice = Path(payload["notice_path"]).read_text()
    assert expect["primary"] in notice and "系统自动生成" in notice

    # 幂等：同参数再跑一次，既有文件不被覆盖，新文件追加 _2
    second = _archive(authenticated_client, job_id, case.id, segments)
    assert second.status_code == 200, second.content[:800]
    assert (complaint_dir / expect["primary"]).read_bytes() != b""
    assert any(p.name.startswith(f"1-传统起诉状（{CASE_NAME}）V4_20260924_2") for p in complaint_dir.iterdir())


def test_archive_without_binding_returns_400(authenticated_client, tmp_path):
    """案件没绑文件夹：端点必须明确报错，不能静默成功。"""
    case = CaseFactory(name=CASE_NAME)
    scan = tmp_path / "scan.pdf"
    segments, _ = _synthetic_scan(scan)
    job_id = _create_job(authenticated_client, scan)

    response = _archive(authenticated_client, job_id, case.id, segments)
    assert response.status_code in (400, 422), response.content[:400]
    assert "未绑定" in response.content.decode("utf-8", "ignore")


def test_archive_write_duplicates_false_skips_copies(authenticated_client, tmp_path):
    """write_duplicates=false：副本不落盘，但仍在响应里报出来。"""
    material = _synthetic_case_tree(tmp_path / "case")
    case = CaseFactory(name=CASE_NAME)
    CaseFolderBinding.objects.create(case=case, folder_path=str(tmp_path / "case"))

    scan = tmp_path / "scan.pdf"
    segments, expect = _synthetic_scan(scan)
    job_id = _create_job(authenticated_client, scan)

    response = _archive(authenticated_client, job_id, case.id, segments, write_duplicates=False)
    assert response.status_code == 200, response.content[:800]
    payload = response.json()

    assert (material / "1-起诉状" / expect["primary"]).is_file()
    assert not (material / "1-起诉状" / DUPLICATE_SUBDIR).exists()
    assert len(payload["duplicates"]) == 1
    assert len(payload["duplicates"][0]) == 3


@pytest.mark.timeout(600)
@pytest.mark.skipif(
    not (os.environ.get("E2E_CASE_DIR") and os.environ.get("E2E_SCAN_PDF")),
    reason="需要 E2E_CASE_DIR / E2E_SCAN_PDF 指向真实材料副本",
)
def test_archive_real_scan_replay(authenticated_client, tmp_path):
    """真实材料回放：把案卷目录复制到 tmp，再用真实扫描件跑一遍。

    断言的是「人工拆分那一次的结论」——6 份文书各归各位、3 份副本进副本目录、
    文件名里的序号/版本/日期与人工归档完全一致。
    """
    case_src = Path(os.environ["E2E_CASE_DIR"])
    scan_src = Path(os.environ["E2E_SCAN_PDF"])
    work = tmp_path / "case"
    shutil.copytree(case_src, work)
    if os.environ.get("E2E_STRIP_EXISTING_PDFS"):
        # 模拟「扫描件刚到、卷宗里只有 docx 草稿」：删掉人工归档过的 pdf，
        # 才能断言系统写出来的文件名与人工那次逐字一致
        for pdf in Path(work).rglob("*.pdf"):
            if any(part.endswith("立案材料") for part in pdf.parts) and pdf.name[:1].isdigit():
                pdf.unlink()
    scan = tmp_path / "scan.pdf"
    shutil.copy2(scan_src, scan)

    material = next(p for p in work.rglob("*立案材料*") if p.is_dir())
    # 案名从既有文件名里取（复制过来的案卷自带 V4 草稿）
    existing = [p.name for p in (material / "1-起诉状").iterdir() if p.is_file()]
    parsed = next(parse_document_name(n) for n in existing if parse_document_name(n))
    case_name = parsed.case_name

    case = CaseFactory(name=case_name)
    CaseFolderBinding.objects.create(case=case, folder_path=str(work))

    segments: list[dict[str, object]] = [
        {"page_start": 1, "page_end": 2, "doc_type": "传统起诉状", "material_type": "complaint"},
        {"page_start": 3, "page_end": 4, "doc_type": "传统起诉状", "material_type": "complaint"},
        {"page_start": 5, "page_end": 6, "doc_type": "传统起诉状", "material_type": "complaint"},
        {"page_start": 7, "page_end": 13, "doc_type": "要素式起诉状", "material_type": "complaint"},
        {"page_start": 14, "page_end": 20, "doc_type": "要素式起诉状", "material_type": "complaint"},
        {"page_start": 21, "page_end": 27, "doc_type": "要素式起诉状", "material_type": "complaint"},
        {
            "page_start": 28,
            "page_end": 29,
            "doc_type": "佛山法院送达地址确认书",
            "material_type": "delivery_address_confirmation",
        },
        {
            "page_start": 34,
            "page_end": 34,
            "doc_type": "财产保全申请书",
            "material_type": "preservation_materials",
        },
        {
            "page_start": 37,
            "page_end": 37,
            "doc_type": "诉讼费退费账号确认书",
            "material_type": "refund_account_confirmation",
        },
        {"page_start": 39, "page_end": 39, "doc_type": "证据清单", "material_type": "evidence_list"},
    ]

    job_id = _create_job(authenticated_client, scan)
    response = _archive(authenticated_client, job_id, case.id, segments)
    assert response.status_code == 200, response.content[:1500]
    payload = response.json()

    written = {item["filename"]: item for item in payload["written"]}
    logger.info("归档结果（%d 个文件）：\n%s", len(_tree(work)), "\n".join(_tree(work)))

    versions = {name.split("V")[1][:1] for name in written}
    assert "4" in versions, f"起诉状应沿用草稿 V4，实际 {versions}"
    complaint_files = [n for n in written if n.startswith("1-传统起诉状")]
    assert len(complaint_files) == 3, complaint_files
    element_files = [n for n in written if n.startswith("2-要素式起诉状")]
    assert len(element_files) == 3, element_files
    assert sum(1 for i in payload["written"] if i["is_duplicate"]) == 4, payload["written"]
    assert Path(payload["notice_path"]).is_file()

    # 正本页数与源页区间一致（切片没串页）
    primary = material / "1-起诉状" / f"1-传统起诉状（{case_name}）V4_20261106.pdf"
    assert primary.is_file(), [p.name for p in (material / "1-起诉状").iterdir()]
    with fitz.open(primary) as doc:
        assert doc.page_count == 2
