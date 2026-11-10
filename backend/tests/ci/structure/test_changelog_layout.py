"""changelog 目录层级守卫。

## 为什么要这个测试

`changelog/` 曾经长出两套结构：`changelog/v27/v27.11/`（正确）与
`changelog/v27.11/`（错误，建在了根下）。同一个规范只写在 CLAUDE.md 里
是拦不住人的——并行会话各自 `ls changelog/` 看到的东西不一样，于是继续
在错的那层建新目录，分叉越拉越宽（v27.11 到 v27.16 全部错位过）。

这条守卫把「根目录只允许主版本目录」变成 CI 会红的硬约束。

## 规则

- `changelog/` 根下只允许 `v{主版本}/` 形式的目录（如 `v26/`、`v27/`）。
- 次版本目录必须嵌在主版本目录内：`changelog/v27/v27.11/`。
- 补丁文件必须落在次版本目录内：`changelog/v27/v27.11/v27.11.0.md`。

**不检查**补丁号是否超过 10：v27.0–v27.10 与 v27.13/v27.14 存在历史超限文件，
属既有存量、不追溯重排；新版本由人工遵守「逢十进一」（见 CLAUDE.md）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CHANGELOG = REPO_ROOT / "changelog"

#: 根下允许的目录名：v27、v28……
_MAJOR_DIR = re.compile(r"^v\d+$")
#: 次版本目录名：v27.11
_MINOR_DIR = re.compile(r"^v(\d+)\.(\d+)$")

#: 历史遗留例外（不追溯修正）：
#: `changelog/v26/v1.0/` 是早期从 v1.0 迁到 v26 时整体搬进来的，版本号仍是 v1.0.*。
#: 动它会改历史版本库的路径，收益极低，故允许存在；新目录不得仿效。
_LEGACY_DIRS = {("26", "1.0")}


def test_changelog_root_only_major_dirs() -> None:
    """changelog/ 根下只允许主版本目录，不允许出现 v27.11 这类次版本目录。"""
    assert CHANGELOG.is_dir(), f"找不到 changelog 目录：{CHANGELOG}"

    offenders = [
        entry.name
        for entry in CHANGELOG.iterdir()
        if entry.is_dir() and not _MAJOR_DIR.match(entry.name)
    ]
    assert not offenders, (
        "changelog/ 根下出现了非主版本目录：" + ", ".join(sorted(offenders)) + "\n"
        "次版本目录必须嵌在主版本目录内，例如 changelog/v27/v27.11/（见 CLAUDE.md「Changelog 规则」）。"
    )


def test_minor_dirs_live_under_matching_major() -> None:
    """v27.11 必须放在 v27/ 下；v28.x 放到 v27/ 里也算错。"""
    problems: list[str] = []

    for major_dir in sorted(p for p in CHANGELOG.iterdir() if p.is_dir() and _MAJOR_DIR.match(p.name)):
        major_version = major_dir.name[1:]  # "27"
        for minor_dir in sorted(p for p in major_dir.iterdir() if p.is_dir()):
            matched = _MINOR_DIR.match(minor_dir.name)
            if matched is None:
                problems.append(f"{minor_dir.relative_to(REPO_ROOT)}：目录名不是 v{{主}}.{{次}} 形式")
                continue
            if (major_version, minor_dir.name[1:]) in _LEGACY_DIRS:
                continue
            if matched.group(1) != major_version:
                problems.append(
                    f"{minor_dir.relative_to(REPO_ROOT)}：主版本号 {matched.group(1)} "
                    f"与所在目录 v{major_version}/ 不一致"
                )

    assert not problems, "changelog 目录层级有问题：\n" + "\n".join(problems)


def test_every_version_file_sits_in_its_minor_dir() -> None:
    """文件必须放在与自己版本号匹配的次版本目录里。"""
    problems: list[str] = []
    file_pattern = re.compile(r"^v(\d+)\.(\d+)\.(\d+)\.md$")

    for path in sorted(CHANGELOG.rglob("*.md")):
        matched = file_pattern.match(path.name)
        if matched is None:
            # 非版本文件（如手工笔记）不在此规则内，但要能看见
            problems.append(f"{path.relative_to(REPO_ROOT)}：文件名不是 v{{主}}.{{次}}.{{补丁}}.md 形式")
            continue

        major, minor, _patch = matched.groups()
        # 历史例外：文件版本号与所在目录不同（见 _LEGACY_DIRS）
        if any(path.parent.name == f"v{legacy_minor}" for _maj, legacy_minor in _LEGACY_DIRS):
            continue
        expected_parent = CHANGELOG / f"v{major}" / f"v{major}.{minor}"
        if path.parent != expected_parent:
            problems.append(
                f"{path.relative_to(REPO_ROOT)}：应放在 "
                f"{expected_parent.relative_to(REPO_ROOT)}/ 下，实际在 {path.parent.relative_to(REPO_ROOT)}/"
            )

    assert not problems, "changelog 文件位置与版本号不匹配：\n" + "\n".join(problems)
