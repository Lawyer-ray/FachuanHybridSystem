"""端到端测试：验证格式规范化输出与参考文档一致

用法: cd backend && .venv/bin/python test_format_e2e.py
"""

import sys
import os

# 设置 Django 环境（LLM 服务需要）
_backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _backend_dir)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.apiSystem.settings")

import django
django.setup()

# 添加 normalizer 路径
sys.path.insert(0, os.path.join(_backend_dir, "apps", "contract_review", "services", "format_normalizer"))

from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
import json

# 测试/验证文档路径
BASE = Path("/Users/huangsong21/Downloads/验收")
PAIRS = [
    {
        "name": "电脑维护合同",
        "test": BASE / "电脑维护合同[测试集].docx",
        "ref": BASE / "电脑维护合同[修订版]V1_20250715[验证集].docx",
    },
    {
        "name": "赛羽自媒体平台代运营服务合同",
        "test": BASE / "赛羽自媒体平台代运营服务合同20250325[测试集].docx",
        "ref": BASE / "赛羽自媒体平台代运营服务合同20250325[修订版]V1_20250326[验证集].docx",
    },
    {
        "name": "项目合作协议（跨境运营顾问）",
        "test": BASE / "项目合作协议（跨境运营顾问）(2.13)[测试集].docx",
        "ref": BASE / "项目合作协议（跨境运营顾问）(2.13)[修订版]V1_2025.02.14[验证集].docx",
    },
]

OUTPUT_DIR = BASE / "test_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def analyze_doc(path: Path) -> dict:
    """分析文档格式"""
    doc = Document(str(path))
    result = {
        "paragraphs": [],
        "sections": [],
        "numbering_defs": [],
    }

    # Section info
    for sec in doc.sections:
        pgMar = sec._sectPr.find(qn("w:pgMar"))
        result["sections"].append({
            "top": pgMar.get(qn("w:top")) if pgMar is not None else None,
            "bottom": pgMar.get(qn("w:bottom")) if pgMar is not None else None,
            "left": pgMar.get(qn("w:left")) if pgMar is not None else None,
            "right": pgMar.get(qn("w:right")) if pgMar is not None else None,
        })

    # Numbering defs
    try:
        np = doc.part.numbering_part._element
        for abstract in np.findall(qn("w:abstractNum")):
            aid = abstract.get(qn("w:abstractNumId"))
            levels = []
            for lvl in abstract.findall(qn("w:lvl")):
                num_fmt = lvl.find(qn("w:numFmt"))
                levels.append({
                    "ilvl": lvl.get(qn("w:ilvl")),
                    "numFmt": num_fmt.get(qn("w:val")) if num_fmt is not None else None,
                })
            result["numbering_defs"].append({"abstractNumId": aid, "levels": levels})
    except:
        pass

    # Paragraphs
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue

        info = {"index": i, "text": text[:60]}

        # Numbering
        pPr = para._element.find(qn("w:pPr"))
        if pPr is not None:
            numPr = pPr.find(qn("w:numPr"))
            if numPr is not None:
                nid = numPr.find(qn("w:numId"))
                ilv = numPr.find(qn("w:ilvl"))
                info["numId"] = nid.get(qn("w:val")) if nid is not None else None
                info["ilvl"] = ilv.get(qn("w:val")) if ilv is not None else None

            # Spacing
            spacing = pPr.find(qn("w:spacing"))
            if spacing is not None:
                info["line"] = spacing.get(qn("w:line"))

            # Indent
            ind = pPr.find(qn("w:ind"))
            if ind is not None:
                fl = ind.get(qn("w:firstLine"))
                if fl:
                    info["firstLine"] = fl

        # Run format
        if para.runs:
            rPr = para.runs[0]._element.find(qn("w:rPr"))
            if rPr is not None:
                rFonts = rPr.find(qn("w:rFonts"))
                if rFonts is not None:
                    ea = rFonts.get(qn("w:eastAsia"))
                    if ea:
                        info["eastAsia"] = ea
                sz = rPr.find(qn("w:sz"))
                if sz is not None:
                    info["sz"] = sz.get(qn("w:val"))
                if rPr.find(qn("w:b")) is not None:
                    info["bold"] = True

        result["paragraphs"].append(info)

    return result


def compare_format(ref_info: dict, out_info: dict, name: str) -> list[str]:
    """比较输出与参考的格式差异"""
    issues = []

    # 1. 页边距
    if ref_info["sections"] and out_info["sections"]:
        ref_sec = ref_info["sections"][0]
        out_sec = out_info["sections"][0]
        for attr in ("top", "bottom", "left", "right"):
            if ref_sec.get(attr) != out_sec.get(attr):
                issues.append(
                    f"页边距 {attr}: 参考={ref_sec.get(attr)}, 输出={out_sec.get(attr)}"
                )

    # 2. 编号定义 - 检查段落是否实际使用了编号
    out_with_num = sum(1 for p in out_info["paragraphs"] if p.get("numId"))
    ref_with_num = sum(1 for p in ref_info["paragraphs"] if p.get("numId"))
    if ref_with_num > 0 and out_with_num == 0:
        issues.append(f"输出无段落使用编号（参考有 {ref_with_num} 个段落有编号）")

    # 3. 段落格式对比（取前30个非空段落）
    ref_paras = ref_info["paragraphs"][:30]
    out_paras = out_info["paragraphs"][:30]

    # 检查编号覆盖率
    out_with_num = sum(1 for p in out_paras if p.get("numId"))
    if out_with_num == 0 and any(p.get("numId") for p in ref_paras):
        issues.append("输出文档无任何段落有编号")

    # 检查 ilvl=0 覆盖率
    ref_h0_count = sum(1 for p in ref_paras if p.get("ilvl") == "0")
    out_h0_count = sum(1 for p in out_paras if p.get("ilvl") == "0")
    if ref_h0_count > 0 and out_h0_count == 0:
        issues.append(f"输出无 ilvl=0 段落（参考有 {ref_h0_count} 个）")

    # 检查 ilvl=1 覆盖率
    ref_h1_count = sum(1 for p in ref_paras if p.get("ilvl") == "1")
    out_h1_count = sum(1 for p in out_paras if p.get("ilvl") == "1")
    if ref_h1_count > 0 and out_h1_count == 0:
        issues.append(f"输出无 ilvl=1 段落（参考有 {ref_h1_count} 个）")

    # 检查字体
    out_fonts = set()
    for p in out_paras:
        if "eastAsia" in p:
            out_fonts.add(p["eastAsia"])
    if not out_fonts:
        issues.append("输出文档无东亚字体设置")

    # 检查手动编号残留
    manual_prefixes = 0
    for p in out_paras:
        text = p["text"]
        if not text:
            continue
        # 检测 "一、", "（一）", "1、", "(1)" 等前缀
        import re
        if re.match(r'^[一二三四五六七八九十]+、', text):
            manual_prefixes += 1
        elif re.match(r'^[（(][一二三四五六七八九十\d]+[)）]', text):
            manual_prefixes += 1
        elif re.match(r'^\d+[、．.]', text):
            manual_prefixes += 1
    if manual_prefixes > 0:
        issues.append(f"输出有 {manual_prefixes} 个段落残留手动编号前缀")

    return issues


def main():
    from apps.contract_review.services.format_normalizer import DocxFormatNormalizer

    all_pass = True
    results = []

    for pair in PAIRS:
        name = pair["name"]
        test_path = pair["test"]
        ref_path = pair["ref"]

        print(f"\n{'='*60}")
        print(f"测试: {name}")
        print(f"  测试集: {test_path.name}")
        print(f"  验证集: {ref_path.name}")

        if not test_path.exists():
            print(f"  ⚠️ 测试文件不存在，跳过")
            continue
        if not ref_path.exists():
            print(f"  ⚠️ 验证文件不存在，跳过")
            continue

        # 执行规范化
        output_path = OUTPUT_DIR / f"{test_path.stem}_规范化.docx"
        normalizer = DocxFormatNormalizer(
            test_path, output_path, reference_path=ref_path
        )
        normalizer.normalize()  # use_llm=True (默认)

        # 分析输出和参考
        ref_info = analyze_doc(ref_path)
        out_info = analyze_doc(output_path)

        # 比较
        issues = compare_format(ref_info, out_info, name)

        print(f"\n  输出文件: {output_path.name}")
        if issues:
            print(f"  ❌ 发现 {len(issues)} 个问题:")
            for issue in issues:
                print(f"    - {issue}")
            all_pass = False
        else:
            print(f"  ✅ 格式一致")

        # 打印段落统计
        out_paras = out_info["paragraphs"]
        h0 = sum(1 for p in out_paras if p.get("ilvl") == "0")
        h1 = sum(1 for p in out_paras if p.get("ilvl") == "1")
        h2 = sum(1 for p in out_paras if p.get("ilvl") == "2")
        total = len(out_paras)
        print(f"  段落统计: 总计={total}, ilvl=0:{h0}, ilvl=1:{h1}, ilvl=2:{h2}")

        # 打印前15个段落
        print(f"\n  前15个段落:")
        for p in out_paras[:15]:
            nid = p.get("numId", "-")
            ilvl = p.get("ilvl", "-")
            bold = "B" if p.get("bold") else " "
            font = p.get("eastAsia", "-")
            sz = p.get("sz", "-")
            print(f"    [{bold}] numId={nid}, ilvl={ilvl}, font={font}, sz={sz} | {p['text']}")

        results.append({"name": name, "issues": issues, "pass": len(issues) == 0})

    # 总结
    print(f"\n{'='*60}")
    print("总结:")
    for r in results:
        status = "✅" if r["pass"] else "❌"
        print(f"  {status} {r['name']}: {len(r['issues'])} 个问题")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
