"""扫描件归档的命名 / 版本对齐 / 副本识别（纯函数，无 IO、无 DB）。

## 为什么单独成模块

「扫描件拆出来怎么命名」有三件事必须一起决定，而它们都是**瞬时计算**：

1. **命名**：`1-传统起诉状（案名）V4_20261106.pdf` —— 序号取「同目录里同一文书的既有序号」，
   版本取「同目录里同一文书的既有版本」，不是无脑 V1 或 +1。律师的工作习惯是：
   docx 是草稿（V4），客户签章回传的扫描件**就是同一版 V4**（不是 V5）。
2. **子目录落位**：材料类型 → 案件文件夹里的哪一层（`1-立案材料/1-起诉状`）。
   目录名带两头括号与序号，且不同模板可能叫「1-起诉状」或「1-起诉状和反诉答辩状」，
   所以只按关键词匹配既有目录，不硬编码全名。
3. **副本识别**：立案材料「一式三份」，三份是**同一文书的重复件**，不是三份不同材料。
   判据只能是页级图像指纹（签章位置会挪、扫描噪点会变，所以要用容差距离，不能哈希全等）。

放在 `apps/cases/services/material/` 而不是 `pdf_splitting`：这些规则描述的是
**案件卷宗的命名约定**，与「怎么把 PDF 切开」无关；归档服务好换，命名约定不该跟着换。

## 边界

本模块只做纯计算：入参是文件名列表 / 页指纹 / 材料类型，出参是序号、版本、路径片段与
副本分组。落盘、权限、事务全部由 `case_material_archive_service` 负责。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Mapping, NamedTuple, Sequence

# ── 命名约定 ────────────────────────────────────────────────────────────────

#: 序号与文书名之间、文书名与案名括号之间的分隔（半角 `-` 是本仓库现行写法）
ORDINAL_SEP = "-"
#: 案名括号用全角（与 `filename_template_service.GENERATED_DOC_DEFAULT` 一致）
PAREN_OPEN = "（"
PAREN_CLOSE = "）"

#: 副本（第 2、3 份）与正本分开存放，避免污染「每类文书一份」的主目录
DUPLICATE_SUBDIR = "其余副本（第2、3份）"

#: 无主目录可归的兜底子目录关键字
FALLBACK_SUBDIR_KEYWORD = "其他立案材料"

#: 材料类型 → 目标子目录关键字（按顺序命中即止；只匹配目录名包含该关键字者）
#:
#: 键是 `pdf_splitting` 模板的 `segment_type`（`template_registry.py:42-303`），
#: 以及案件材料库里人工填写的 `type_name` 常见写法。
SUBDIR_KEYWORDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("complaint", "起诉状"), ("起诉状",)),
    (("evidence", "证据清单", "证据明细", "证据目录"), ("证据",)),
    (("preservation", "保全"), ("保全",)),
    (("identity", "身份证明", "主体信息", "身份材料"), ("身份证明", "主体信息")),
    (("authorization", "委托", "授权", "所函"), ("委托",)),
    (("service_address", "delivery_address", "送达地址"), ("送达地址",)),
    (("refund", "退费"), ("退费",)),
)

_FILENAME_RE = re.compile(
    r"^(?P<ordinal>\d+)" + re.escape(ORDINAL_SEP) + r"(?P<doc_type>.+?)"
    r"[（(](?P<case_name>.*)[）)]"
    r"V(?P<version>\d+)_(?P<date>\d{8})"
    r"\.(?P<ext>[A-Za-z0-9]+)$"
)


class ParsedDocumentName(NamedTuple):
    """从「序号-文书名（案名）V版本_日期.pdf」解析出的各段。"""

    ordinal: int
    doc_type: str
    case_name: str
    version: int
    date: str
    ext: str


class TargetName(NamedTuple):
    """归档目标（序号 + 版本），由目录里既有文件推断。"""

    ordinal: int
    version: int
    #: 是否命中了同类型的既有文件（命中＝沿用其序号与版本；未命中＝新文书）
    matched_existing: bool


def _nfkc(text: str) -> str:
    """归一全/半角与空白，避免「（」写成「(」导致匹配不上。"""
    return unicodedata.normalize("NFKC", text or "").strip()


def parse_document_name(filename: str) -> ParsedDocumentName | None:
    """解析本仓库的文书文件名；不符合约定时返回 None（调用方跳过即可）。

    兼容半角括号与全角括号（历史文件两种都有）。
    """
    name = _nfkc(filename)
    match = _FILENAME_RE.match(name)
    if not match:
        return None
    return ParsedDocumentName(
        ordinal=int(match.group("ordinal")),
        doc_type=match.group("doc_type"),
        case_name=match.group("case_name"),
        version=int(match.group("version")),
        date=match.group("date"),
        ext=match.group("ext").lower(),
    )


def infer_target_name(
    existing_names: Iterable[str],
    *,
    doc_type: str,
    case_name: str = "",
) -> TargetName:
    """按「同目录里同一文书的既有序号/版本」推断本次归档该用什么。

    规则（与律师实际习惯一致，不是 +1）：

    - 命中文书名相同的既有文件 → **沿用其序号**，版本取其中最大值
      （docx 是 V4 草稿、扫描件是 V4 签章件，同名同版，不是 V5）。
    - 未命中 → 序号取「已有最大序号 + 1」（空目录则 1），版本 1。
    - `case_name` 仅用于优先匹配同名案件的文件；留空则不区分。

    序号冲突时（同一序号被别的文书占用）顺延到下一个空位，避免出现两个 `1-`。
    """
    target_doc = _nfkc(doc_type)
    target_case = _nfkc(case_name)
    parsed = [p for p in (parse_document_name(n) for n in existing_names) if p is not None]

    same_doc = [p for p in parsed if p.doc_type == target_doc]
    if target_case:
        same_case = [p for p in same_doc if _nfkc(p.case_name) == target_case]
        same_doc = same_case or same_doc

    if same_doc:
        ordinal = min(p.ordinal for p in same_doc)
        return TargetName(ordinal=ordinal, version=max(p.version for p in same_doc), matched_existing=True)

    used_ordinals = {p.ordinal for p in parsed}
    next_ordinal = len(used_ordinals) + 1
    while next_ordinal in used_ordinals:
        next_ordinal += 1
    return TargetName(ordinal=next_ordinal, version=1, matched_existing=False)


def build_archive_name(
    *,
    ordinal: int,
    doc_type: str,
    case_name: str,
    version: int,
    date: str,
    ext: str = "pdf",
) -> str:
    """拼出 `1-传统起诉状（案名）V4_20261106.pdf`。

    `date` 必须是 8 位 `YYYYMMDD`；这里只做长度校验，不做日期解析
    （日期语义由调用方决定：版本日期，不是归档日期）。
    """
    if ordinal < 1:
        raise ValueError(f"序号必须从 1 开始：{ordinal}")
    if version < 1:
        raise ValueError(f"版本必须从 1 开始：{version}")
    if not (len(date) == 8 and date.isdigit()):
        raise ValueError(f"日期必须是 8 位 YYYYMMDD：{date!r}")
    return f"{ordinal}{ORDINAL_SEP}{doc_type}{PAREN_OPEN}{case_name}{PAREN_CLOSE}V{version}_{date}.{ext.lstrip('.')}"


def resolve_subdir(available_subdirs: Sequence[str], material_type: str) -> str | None:
    """把材料类型映射到**实际存在**的子目录名；无匹配返回 None（调用方走兜底）。

    只按关键字命中，不硬编码目录全名——不同文件夹模板的节点名不同
    （`1-起诉状` vs `1-起诉状和反诉答辩状`），硬编码会在换模板时静默落错位置。
    """
    if not available_subdirs:
        return None
    material_type = _nfkc(material_type).lower()

    candidates: tuple[str, ...] = ()
    for keys, keywords in SUBDIR_KEYWORDS:
        if any(k.lower() in material_type for k in keys):
            candidates = keywords
            break
    if not candidates:
        return None

    for keyword in candidates:
        for subdir in available_subdirs:
            if keyword in _nfkc(subdir):
                return subdir
    return None


def fallback_subdir(available_subdirs: Sequence[str]) -> str | None:
    """兜底子目录：优先「其他立案材料」，否则任意「其他…」，否则 None。"""
    for subdir in available_subdirs:
        if FALLBACK_SUBDIR_KEYWORD in _nfkc(subdir):
            return subdir
    for subdir in available_subdirs:
        if "其他" in _nfkc(subdir):
            return subdir
    return None


# ── 副本识别 ────────────────────────────────────────────────────────────────

#: 页指纹比对阈值：**多页文书**（真副本实测 ≤0.024，非同页 ≥0.042）。
#:
#: 实测来自 2026-11-24 一份真实 40 页立案材料扫描件（同一文书回传 3 份）：
#: 指纹口径为「逐页二值化 → 100dpi → 8px block 墨占比 → 平均绝对差」。
#:
#:   真副本（6 对）      0.008 ~ 0.024
#:   非同页（4 对）      0.042 ~ 0.049
#:
#: 为什么不取更低分辨率：36dpi/16×16 与 36dpi/24×24 两种灰度方案在这批样本上
#: **排序是反的**（真副本 0.003–0.012、不同文书 0.008–0.017，完全重叠），
#: 因为密集中文版式在低分辨率下同构、而距离又被纸张亮度主导。
SAME_PAGE_MAX_DISTANCE = 0.03

#: **单页文书**的阈值更严：单页只有一次独立证据，误判成本全压在这一页上。
#:
#: 实测里有一对不同的单页文书距离 0.027，落在多页阈值 0.03 以内；收紧到 0.02
#: 后它不再被判为副本。多页文书要「逐页全中」，误判概率天然低得多，故不收紧。
SINGLE_PAGE_MAX_DISTANCE = 0.02


def signature_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """两个页指纹的平均绝对差（0–1）。长度不一致视为完全不同（返回 1.0）。"""
    if not a or not b or len(a) != len(b):
        return 1.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def pages_match(a: Sequence[float], b: Sequence[float], *, max_distance: float = SAME_PAGE_MAX_DISTANCE) -> bool:
    """两页是否「同一页」（容忍签章位置与扫描噪点差异）。"""
    return signature_distance(a, b) <= max_distance


def documents_match(
    a: Sequence[Sequence[float]],
    b: Sequence[Sequence[float]],
    *,
    max_distance: float = SAME_PAGE_MAX_DISTANCE,
) -> bool:
    """两份文档是否逐页同一（页数必须一致）。"""
    if len(a) != len(b) or not a:
        return False
    return all(pages_match(x, y, max_distance=max_distance) for x, y in zip(a, b))


def page_aware_max_distance(page_count: int) -> float:
    """按页数取阈值：单页更严（见 `SINGLE_PAGE_MAX_DISTANCE` 的实测理由）。"""
    return SINGLE_PAGE_MAX_DISTANCE if page_count <= 1 else SAME_PAGE_MAX_DISTANCE


def group_copies(
    documents: Mapping[str, Sequence[Sequence[float]]],
    *,
    max_distance: float | None = None,
) -> list[list[str]]:
    """把内容相同的文书分到一组，返回**只有 2 份以上**的分组。

    输入/输出都用调用方给的键（一般是段 id），保持顺序稳定：
    组内第一个元素是「正本」，其后是副本；组的先后按首次出现顺序。

    `max_distance` 留空时按页数自动取（`page_aware_max_distance`）：单页更严。
    调用方显式给值则一律用它（测试与特殊批处理需要可控阈值）。
    """
    groups: list[list[str]] = []
    for key, pages in documents.items():
        for group in groups:
            threshold = max_distance if max_distance is not None else page_aware_max_distance(len(pages))
            if documents_match(pages, documents[group[0]], max_distance=threshold):
                group.append(key)
                break
        else:
            groups.append([key])
    return [g for g in groups if len(g) > 1]
