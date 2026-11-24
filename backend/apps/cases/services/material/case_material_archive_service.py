"""归档落盘服务：把拆解好的扫描件写进案件绑定的「立案材料」目录。

## 谁是唯一的写磁盘方

`scan_archive_naming` 只算「叫什么、落到哪个子目录、哪几份是副本」，一行磁盘操作都没有；
真正 `open(..., "wb")` 的只有本服务。其它调用方一律走 `archive()`，不要各自再写一份落盘
逻辑——否则「不覆盖」「副本目录」「核对说明」这三件事会各写各的，卷宗迟早出现两种规矩。

## 三件容易写错的事

1. **不覆盖**：目标文件名已存在时追加 `_2`、`_3`。律师会留着上一轮归档结果做对照，
   覆盖等于销毁原件，且不可逆。
2. **副本只认页指纹**：`page_signatures` 相同的若干份是同一份文书的重复件（一式三份），
   组内第一份进主目录（正本），其余进 `其余副本（第2、3份）` 并带 `（第N份）` 后缀；
   没有指纹的一律当正本——宁可多留一份，也不能把两份不同材料合成一份。
3. **立案材料目录靠关键字定位**：模板节点名带序号且各家不同（`1-立案材料` /
   `2-立案材料（一审）`），所以浅层优先按关键字找，找不到就用绑定根本身。

## 建目录的边界

只在既有「立案材料」目录下补建缺的目标子目录；绑定根不可访问直接抛
`ValidationException`，绝不替用户把整棵案件目录树建出来——那样的空目录树对律师只是
噪声，还会把「什么都没做」伪装成「归档成功」。
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

from apps.cases.models import Case
from apps.cases.services.material.scan_archive_naming import (
    DUPLICATE_SUBDIR,
    PAREN_CLOSE,
    PAREN_OPEN,
    build_archive_name,
    fallback_subdir,
    group_copies,
    infer_target_name,
    resolve_subdir,
)
from apps.cases.services.template.folder_binding_service import CaseFolderBindingService
from apps.core.exceptions import NotFoundError, ValidationException

logger = logging.getLogger(__name__)

#: 「立案材料」目录的节点名关键字（序号前缀各家模板不同，只认关键字）
MATERIAL_DIR_KEYWORD = "立案材料"

#: 从绑定根往下找「立案材料」的最大层数：够得着 `3-一审/1-立案材料`，
#: 又不会把整棵阶段目录树走一遍（大案卷宗轻松上万文件）
MAX_MATERIAL_DIR_DEPTH = 4

#: 核对说明文件名：`00-` 前缀保证它排在本目录所有材料文件之前
NOTICE_FILENAME = "00-拆分与核对说明.md"


@dataclass(frozen=True)
class ArchiveItem:
    """一份待落盘的扫描件（一条拆解结果）。

    `material_type` 是 `pdf_splitting` 的 `segment_type` 或人工填的 `type_name`，
    只用于映射目标子目录；`subdir` 非空时直接用它，不再看 `material_type`。
    `page_signatures` 是页级图像指纹，只有它能判定「这几份是同一份文书的重复件」。
    """

    doc_type: str
    material_type: str
    content: bytes
    page_signatures: Sequence[Sequence[float]] = ()
    subdir: str = ""


@dataclass
class ArchivedFile:
    """一份落盘成功的文书（`subdir` 相对绑定根给出，便于直接展示）。"""

    filename: str
    subdir: str
    absolute_path: str
    is_duplicate: bool


@dataclass
class ArchiveResult:
    """一次归档的结果：写成了什么、哪几组是重复件、哪些没写、核对说明在哪。"""

    root: str
    written: list[ArchivedFile] = field(default_factory=list)
    #: 每组重复件的 doc_type 列表（组内第一份是正本）
    duplicates: list[list[str]] = field(default_factory=list)
    #: 未归档条目：`{"doc_type": ..., "reason": ...}`
    skipped: list[dict[str, str]] = field(default_factory=list)
    notice_path: str | None = None


class _Placement(NamedTuple):
    """目标目录定不下来时 `directory is None` + `reason` 说明缘由。"""

    directory: Path | None
    reason: str = ""


class _Outcome(NamedTuple):
    """单份文书的落盘结果；`archived is None` 表示被跳过。"""

    archived: ArchivedFile | None
    reason: str = ""


class _NoticeRow(NamedTuple):
    """核对说明表格的一行（字节数取实际写入的 content 长度）。"""

    doc_type: str
    subdir: str
    filename: str
    size: int
    is_duplicate: bool


def _cell(text: str) -> str:
    """Markdown 表格单元格：竖线会把列切断，换成全角。"""
    return str(text).replace("|", "｜")


class CaseMaterialArchiveService:
    """把拆解好的扫描件写进案件绑定的「立案材料」目录（唯一写磁盘的一方）。"""

    def __init__(self, binding_service: CaseFolderBindingService | None = None) -> None:
        """支持注入绑定服务（测试与上层复用）；默认即时构造。"""
        self._binding_service = binding_service

    @property
    def binding_service(self) -> CaseFolderBindingService:
        if self._binding_service is None:
            self._binding_service = CaseFolderBindingService()
        return self._binding_service

    def archive(
        self,
        *,
        case_id: int,
        items: Sequence[ArchiveItem],
        date: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        write_duplicates: bool = True,
        write_notice: bool = True,
    ) -> ArchiveResult:
        """把 `items` 逐份写进案件卷宗，返回写入明细。

        `date` 是 8 位 `YYYYMMDD`，只用于文件名里的版本日期与核对说明落款。

        `write_duplicates=False` 时副本（同组第 2、3 份）**不落盘**，但仍会出现在
        `ArchiveResult.duplicates` 里——调用方据此提示「另有 N 份未写入」，不至于
        静默丢掉信息。正本永远写。
        权限校验不在本服务：`user` / `org_access` / `perm_open_access` 原样交给
        `CaseFolderBindingService.get_binding()`，它同时保证「案件存在且本人可访问」。
        """
        binding = self.binding_service.get_binding(
            case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        folder_path = str(getattr(binding, "resolved_folder_path", "") or "").strip() if binding is not None else ""
        if not folder_path:
            raise ValidationException(
                message="案件未绑定文件夹",
                code="CASE_FOLDER_NOT_BOUND",
                errors={"case_id": case_id},
            )

        case = self._load_case(case_id)
        # resolve() 之后所有派生路径都在同一个坐标系里，`relative_to(root)` 才可靠
        root = Path(folder_path).expanduser().resolve()
        material_dir = self._locate_material_dir(root)
        if not material_dir.is_dir():
            raise ValidationException(
                message="案件文件夹不可访问",
                code="CASE_FOLDER_INACCESSIBLE",
                errors={"folder_path": str(material_dir)},
            )

        subdir_names = self._subdir_names(material_dir)
        copy_groups = self._copy_groups(items)
        copy_numbers = {index: position for group in copy_groups for position, index in enumerate(group, start=1)}
        # 同一次归档里已占用的文件名：磁盘枚举看不到本次刚写的，必须单独记账
        claimed: dict[Path, set[str]] = {}

        written: list[ArchivedFile] = []
        rows: list[_NoticeRow] = []
        skipped: list[dict[str, str]] = []
        for index, item in enumerate(items):
            copy_no = copy_numbers.get(index, 1)
            if copy_no >= 2 and not write_duplicates:
                logger.info(
                    "扫描件副本未落盘（write_duplicates=False）: doc_type=%s, 第%s份",
                    item.doc_type,
                    copy_no,
                )
                continue
            outcome = self._archive_item(
                item=item,
                copy_no=copy_no,
                root=root,
                material_dir=material_dir,
                subdir_names=subdir_names,
                case_name=case.name,
                date=date,
                claimed=claimed,
            )
            if outcome.archived is None:
                logger.warning("扫描件归档跳过: doc_type=%s, reason=%s", item.doc_type, outcome.reason)
                skipped.append({"doc_type": item.doc_type, "reason": outcome.reason})
                continue
            written.append(outcome.archived)
            rows.append(
                _NoticeRow(
                    doc_type=item.doc_type,
                    subdir=outcome.archived.subdir,
                    filename=outcome.archived.filename,
                    size=len(item.content),
                    is_duplicate=outcome.archived.is_duplicate,
                )
            )

        notice_path = self._write_notice(material_dir, date=date, rows=rows, skipped=skipped) if write_notice else None
        logger.info(
            "扫描件归档完成: case_id=%s, 目录=%s, 写入=%s, 跳过=%s",
            case_id,
            material_dir,
            len(written),
            len(skipped),
        )
        return ArchiveResult(
            root=str(root),
            written=written,
            duplicates=[[items[index].doc_type for index in group] for group in copy_groups],
            skipped=skipped,
            notice_path=notice_path,
        )

    # ── 落盘 ────────────────────────────────────────────────────────────────

    def _archive_item(
        self,
        *,
        item: ArchiveItem,
        copy_no: int,
        root: Path,
        material_dir: Path,
        subdir_names: Sequence[str],
        case_name: str,
        date: str,
        claimed: dict[Path, set[str]],
    ) -> _Outcome:
        """写一份文书；`copy_no >= 2` 表示它是同组重复件里的第 2、3 份。"""
        if not item.content:
            return _Outcome(None, "内容为空")

        placement = self._placement(material_dir, subdir_names, item)
        if placement.directory is None:
            return _Outcome(None, placement.reason)
        target_dir = placement.directory
        write_dir = target_dir if copy_no < 2 else target_dir / DUPLICATE_SUBDIR

        # 序号/版本按**主目录**推断：副本与正本是同一份文书，必须共用序号与版本，
        # 而副本目录里的文件名带 `（第N份）`，拿去解析反而会算错
        target = infer_target_name(
            self._known_names(target_dir, claimed),
            doc_type=item.doc_type,
            case_name=case_name,
        )
        filename = build_archive_name(
            ordinal=target.ordinal,
            # 命中同名文书时用卷宗里的写法（「退费账户确认书」而不是拆解侧的
            # 「诉讼费用退费账户确认书」），避免同一份材料在卷宗里出现两种叫法
            doc_type=target.doc_type or item.doc_type,
            case_name=case_name,
            version=target.version,
            # 命中同名文书时用它的版本日期（V4_20261106 的草稿 → 签章件也是
            # V4_20261106）；未命中才是新文书，用调用方给的归档日期
            date=target.date or date,
        )
        if copy_no >= 2:
            filename = self._with_suffix_marker(filename, f"{PAREN_OPEN}第{copy_no}份{PAREN_CLOSE}")

        write_dir.mkdir(parents=True, exist_ok=True)
        filename = self._unique_name(write_dir, filename, claimed)
        path = write_dir / filename
        with path.open("wb") as handle:
            handle.write(item.content)
        claimed.setdefault(write_dir, set()).add(filename)

        logger.info("扫描件已归档: path=%s, 副本=%s", path, copy_no >= 2)
        return _Outcome(
            ArchivedFile(
                filename=filename,
                subdir=self._relative_label(root, write_dir),
                absolute_path=str(path),
                is_duplicate=copy_no >= 2,
            )
        )

    def _placement(self, material_dir: Path, subdir_names: Sequence[str], item: ArchiveItem) -> _Placement:
        """定目标子目录：`item.subdir` → 材料类型映射 → 兜底子目录 → 立案材料目录本身。"""
        if item.subdir:
            directory = self._confined_dir(material_dir, item.subdir)
            if directory is None:
                return _Placement(None, f"子目录越界：{item.subdir}")
            return _Placement(directory)

        name = resolve_subdir(subdir_names, item.material_type) or fallback_subdir(subdir_names)
        if name is not None:
            directory = self._confined_dir(material_dir, name)
            if directory is None:
                return _Placement(None, f"子目录越界：{name}")
            return _Placement(directory)

        if not subdir_names:
            # 立案材料目录下没有子目录（模板未建层级）：直接落在它本身
            return _Placement(material_dir)
        return _Placement(None, f"未找到匹配的子目录：{item.material_type}")

    def _confined_dir(self, material_dir: Path, name: str) -> Path | None:
        """把子目录名收敛到立案材料目录内；`..` 或符号链接逃逸一律返回 None。"""
        candidate = (material_dir / name).resolve()
        try:
            candidate.relative_to(material_dir)
        except ValueError:
            return None
        return candidate

    def _known_names(self, directory: Path, claimed: Mapping[Path, set[str]]) -> list[str]:
        """推断序号/版本要看的既有文件名：磁盘上的 + 本次已写入的。"""
        names: list[str] = []
        if directory.is_dir():
            try:
                names = [child.name for child in directory.iterdir()]
            except OSError:
                logger.warning("枚举目标子目录失败，退化为只看本次已写入的文件: %s", directory)
        names.extend(sorted(claimed.get(directory, set())))
        return names

    def _unique_name(self, directory: Path, filename: str, claimed: Mapping[Path, set[str]]) -> str:
        """目标文件名被占用时追加 `_2`、`_3`……绝不覆盖既有文件。"""
        taken = claimed.get(directory, set())
        candidate = filename
        counter = 2
        while candidate in taken or (directory / candidate).exists():
            candidate = self._with_suffix_marker(filename, f"_{counter}")
            counter += 1
        return candidate

    def _with_suffix_marker(self, filename: str, marker: str) -> str:
        """在扩展名前插标记：`1-起诉状（案名）V4_20261106.pdf` → `…V4_20261106_2.pdf`。"""
        path = Path(filename)
        return f"{path.stem}{marker}{path.suffix}"

    def _relative_label(self, root: Path, directory: Path) -> str:
        """展示用的子目录：相对绑定根（如 `3-一审/1-立案材料/1-起诉状`）。"""
        try:
            return directory.relative_to(root).as_posix()
        except ValueError:
            return str(directory)

    # ── 目录发现 ────────────────────────────────────────────────────────────

    def _locate_material_dir(self, root: Path) -> Path:
        """从绑定根浅层优先找「立案材料」目录；找不到就用绑定根本身。"""
        queue: deque[tuple[Path, int]] = deque([(root, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth and MATERIAL_DIR_KEYWORD in current.name:
                return current
            if depth >= MAX_MATERIAL_DIR_DEPTH:
                continue
            queue.extend((child, depth + 1) for child in self._child_dirs(current))
        return root

    def _child_dirs(self, directory: Path) -> list[Path]:
        try:
            return sorted((child for child in directory.iterdir() if child.is_dir()), key=lambda p: p.name)
        except OSError:
            logger.warning("列举案件目录失败，跳过该层: %s", directory)
            return []

    def _subdir_names(self, material_dir: Path) -> list[str]:
        return [child.name for child in self._child_dirs(material_dir)]

    # ── 副本分组 ────────────────────────────────────────────────────────────

    def _copy_groups(self, items: Sequence[ArchiveItem]) -> list[list[int]]:
        """按页指纹把「同一份文书的重复件」分组，组内条目下标有序（第一个是正本）。

        **只在同名文书内部比对**（`doc_type` 必须完全一致）。仅靠图像距离区分不了
        版式相近的不同单页表格：送达地址确认书与退费账号确认书都是「一页表头 + 表格」，
        像素级相似度可能高于同一份文书的两份扫件；而尾部这些表格的文书名本来就不一样。
        端到端测试就是这个组合报出来的错（把两份不同文书并成了一组）。

        没有 `page_signatures` 的条目一律不参与——判不了就当正本，宁可多留一份。
        """
        by_doc_type: dict[str, dict[str, list[list[float]]]] = {}
        for index, item in enumerate(items):
            if not item.page_signatures:
                continue
            key = item.doc_type.strip()
            by_doc_type.setdefault(key, {})[str(index)] = [list(page) for page in item.page_signatures]

        groups: list[list[int]] = []
        for signatures in by_doc_type.values():
            if len(signatures) < 2:
                continue
            groups.extend([int(key) for key in group] for group in group_copies(signatures))
        # 组内/组间都按原始顺序：下游用 copy_no 算「第N份」，顺序不稳会写出不同的文件名
        return sorted((sorted(group) for group in groups), key=lambda group: group[0])

    # ── 核对说明 ────────────────────────────────────────────────────────────

    def _write_notice(
        self,
        material_dir: Path,
        *,
        date: str,
        rows: Sequence[_NoticeRow],
        skipped: Sequence[Mapping[str, str]],
    ) -> str:
        """在立案材料目录写 `00-拆分与核对说明.md`（律师据此核对落位与命名）。"""
        lines = [
            "# 拆分与核对说明",
            "",
            f"本文件由系统自动生成（归档日期：{date}）。请按本表核对每份文书的落位与命名。",
            "",
            "| 序号 | 文书名 | 目标子目录 | 文件名 | 字节数 | 是否副本 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for index, row in enumerate(rows, start=1):
            lines.append(
                f"| {index} | {_cell(row.doc_type)} | {_cell(row.subdir)} | {_cell(row.filename)} "
                f"| {row.size} | {'是' if row.is_duplicate else '否'} |"
            )
        if skipped:
            lines.extend(["", "## 未归档条目", ""])
            lines.extend(f"- {_cell(item['doc_type'])}：{_cell(item['reason'])}" for item in skipped)

        path = material_dir / NOTICE_FILENAME
        with path.open("wb") as handle:
            handle.write(("\n".join(lines) + "\n").encode("utf-8"))
        return str(path)

    # ── 案件 ────────────────────────────────────────────────────────────────

    def _load_case(self, case_id: int) -> Case:
        """取案名（文件名里要带）。权限已由绑定服务在 `get_binding()` 里校验过。"""
        case = Case.objects.filter(id=case_id).first()
        if case is None:
            raise NotFoundError(
                message="案件不存在",
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {case_id} 的案件不存在"},
            )
        return case
