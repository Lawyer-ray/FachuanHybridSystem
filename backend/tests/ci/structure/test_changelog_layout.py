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

**检查**「逢十进一」（`test_patch_number_never_exceeds_ten`）：同一条线里第三位最大 10
（`v27.4.10` 合法），出现 `.11` 起就是该进位没进位。
存量豁免：v27.0–v27.20 有 `.11`～`.25` 的历史超限文件（v27.7 到 `.25`、v27.10 到 `.22`），
属规则生效前的存量、不追溯重排——所以本守卫只从 `v27.21` 起生效。

**检查**次版本的下号是在创建那一刻取的（`test_new_minor_is_created_in_order`）：
`PIT-026` 的形态是「v27.26.3 之后直接写出 v27.28.0，v27.27 两小时后才补」——
`ls | sort -V` 看不出异常，只有 `git log --reverse` 能看出「号比它大的先提交」。
存量豁免：本守卫从 `v27.33` 起生效（v27.32.0 曾先于 v27.31.0 提交，属该规则生效前的
最后一次事故，留档不追溯）。

**只检查**最新那一段次版本有没有整号跳过（`test_no_skipped_minor_at_the_top`）；
更早的历史缺口（`v27.17`、`v26.49`）同样是存量，不追溯。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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

#: 「逢十进一」从哪个 (主, 次) 起由机器守。更早的是规则生效前的存量：
#: v27.7 到 `.25`、v27.10 到 `.22`、v27.13 到 `.14`、v27.20 到 `.14`……
#: 追溯重排等于改历史版本库路径，收益为零。
_PATCH_CEILING_RULE_FROM = (27, 21)

#: 「次版本下号必须在创建那一刻取」从哪个次版本起由机器守。
#: v27.32.0 曾先于 v27.31.0 提交（2026-11-28 09:25 vs 09:37，PIT-026 同型），
#: 是该规则生效前的最后一次事故，留档不追溯。
_MINOR_ORDER_RULE_FROM = 33


def test_changelog_root_only_major_dirs() -> None:
    """changelog/ 根下只允许主版本目录，不允许出现 v27.11 这类次版本目录。"""
    assert CHANGELOG.is_dir(), f"找不到 changelog 目录：{CHANGELOG}"

    offenders = [entry.name for entry in CHANGELOG.iterdir() if entry.is_dir() and not _MAJOR_DIR.match(entry.name)]
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


def test_no_skipped_minor_at_the_top() -> None:
    """最新的次版本只能是「第二新的 + 1」，不许整段跳过一个次版本。

    2026-11-27 实证：`v27.26.3` 之后直接写出 `v27.28.0`——`v27.27` 目录当时根本不存在，
    两个半小时后才补上 `v27.27.0`。`ls changelog/v27 | sort -V` 看着毫无异常，只有
    `git log` 能看出「号比它大的先提交」；而一旦按 `ls` 取号，后面每一份都建在错的地基上。

    只查最顶上那一段：更早的缺口（`v27.17`、`v26.49`）是存量，不追溯（与「逢十进一」的
    存量例外同一个理由）。
    """
    problems: list[str] = []

    for major_dir in sorted(p for p in CHANGELOG.iterdir() if p.is_dir() and _MAJOR_DIR.match(p.name)):
        major_version = major_dir.name[1:]  # "27"
        minors: list[int] = []
        for minor_dir in major_dir.iterdir():
            matched = _MINOR_DIR.match(minor_dir.name)
            if matched is None:
                continue
            if (major_version, minor_dir.name[1:]) in _LEGACY_DIRS:
                continue
            minors.append(int(matched.group(2)))

        if len(minors) < 2:
            continue
        minors.sort()
        newest, second_newest = minors[-1], minors[-2]
        if newest > second_newest + 1:
            missing = "、".join(f"v{major_version}.{n}" for n in range(second_newest + 1, newest))
            problems.append(f"{major_dir.name}：已有最新次版本 v{major_version}.{newest}，但 {missing} 从未存在")

    assert not problems, (
        "次版本号被跳过了（写新版本前先 `ls changelog/v{X}/` 取最新号，次版本只许 +1）：\n"
        + "\n".join(problems)
        + "\n见 docs/harness/changelog.md §1.1（minor 只有两个合法升位理由）。"
    )


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


# ══════════════════════════════════════════════════════════════════════════
# 「逢十进一」与「次版本下号」两条人工规则，改成机器守
# ══════════════════════════════════════════════════════════════════════════
#
# 这两条原先只写在 `docs/harness/changelog.md` §1.1 里，靠人记。实测的失效方式
# 不是「有人算错」，而是**并行会话各自取号**：A 看到最新是 v27.30.x 就写 v27.31.0，
# B 同时在另一个 worktree 看到还是 v27.28 → 写下 v27.32.0（跳过了 31）。
# 事后再看目录毫无异常，只有 `git log --reverse` 能复原当时的顺序。
#
# 所以下面拆成「纯函数 + 两个薄壳」：判定逻辑可以用假数据单测（不需要真 git），
# 真数据只负责喂给它们。这样 negative case 是真测过的，不是靠信。

_VERSION_FILE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)\.md$")

#: git 的绝对路径。用 which 解析而不是直接写 "git"：ruff 的 S607 要求全路径，
#: 且解析失败时能明确 skip（而不是抛 FileNotFoundError 伪装成"测试挂了"）。
_GIT = shutil.which("git")


def _patch_ceiling_problems(versions: list[tuple[int, int, int]]) -> list[str]:
    """「逢十进一」：同一条线里第三位最大 10（`.11` 起就是没进位）。

    `versions` 是 (主, 次, 补丁) 三元组；只对 `>= _PATCH_CEILING_RULE_FROM` 生效。
    """
    problems: list[str] = []
    for major, minor, patch in versions:
        if (major, minor) < _PATCH_CEILING_RULE_FROM:
            continue
        if patch >= 11:
            problems.append(
                f"v{major}.{minor}.{patch}：第三位超过 10——该进位了，"
                f"应写成 v{major}.{minor + 1}.0（见 changelog.md §1.1 的「逢十进一」）"
            )
    return problems


def _minor_order_problems(sequence: list[tuple[int, int, str]]) -> list[str]:
    """次版本下号必须在**创建那一刻**取「当前最大 + 1」。

    `sequence` 是 (次, 补丁, 提交) 三元组，按 `git log --reverse` 的提交顺序。
    只对 `minor >= _MINOR_ORDER_RULE_FROM` 生效。

    两类问题：
    - **跳号**：写下 minor 时，它比当时的最大次版本还大 1 以上（PIT-026）；
    - **同线倒退**：同一条线里补丁号比先前已提交的更小（v27.28.5 之后又提交 v27.28.3）。
    """
    problems: list[str] = []
    max_minor: int | None = None
    max_patch: dict[int, int] = {}
    for minor, patch, commit in sequence:
        if max_minor is None:
            max_minor = minor
            max_patch[minor] = patch
            continue
        if minor > max_minor + 1 and minor >= _MINOR_ORDER_RULE_FROM:
            problems.append(
                f"{commit} 写下 v27.{minor}.{patch}，但当时最大次版本是 v27.{max_minor}"
                f"——应写 v27.{max_minor + 1}.0（跳过了 v27.{max_minor + 1}）"
            )
        max_minor = max(max_minor, minor)
        if minor in max_patch and patch < max_patch[minor]:
            problems.append(
                f"{commit} 提交 v27.{minor}.{patch}，但 v27.{minor}.{max_patch[minor]} 已先提交"
                f"——同一条线的补丁号必须按提交顺序递增"
            )
        max_patch[minor] = max(max_patch.get(minor, patch), patch)
    return problems


def _all_version_numbers() -> list[tuple[int, int, int]]:
    """现有全部版本文件 → (主, 次, 补丁) 列表（含 legacy 目录，由判定函数自己豁免）。"""
    versions: list[tuple[int, int, int]] = []
    for path in sorted(CHANGELOG.rglob("*.md")):
        matched = _VERSION_FILE.match(path.name)
        if matched is not None:
            major, minor, patch = matched.groups()
            versions.append((int(major), int(minor), int(patch)))
    return versions


def _branch_changelog_order() -> list[tuple[int, int, str]] | None:
    """本分支**新增** changelog 文件的提交顺序；取不到基线时返回 None。

    只用 `--diff-filter=A`：同一份文件后续被补充修订（如 v27.30.0 被改过两次）
    不该重复参与定号。浅克隆或没有基线引用时返回 None（调用方 skip，不空跑成绿）。
    """
    if _GIT is None:
        return None
    # PR 上 `GITHUB_BASE_REF` 就是目标分支名（"main"），比猜 "origin/main" 稳；
    # 本地则退回 origin/main / main。三条都取不到才 skip。
    pr_base = os.environ.get("GITHUB_BASE_REF")
    for base in (
        os.environ.get("CHANGELOG_BASE_REF"),
        f"origin/{pr_base}" if pr_base else None,
        "origin/main",
        "main",
    ):
        if not base:
            continue
        probe = subprocess.run(
            [_GIT, "rev-parse", "--verify", "--quiet", base],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            continue
        log = subprocess.run(
            [
                _GIT, "log", "--reverse", "--diff-filter=A", "--format=COMMIT %h",
                "--name-only", f"{base}..HEAD", "--", "changelog/",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if log.returncode != 0:
            continue
        sequence: list[tuple[int, int, str]] = []
        commit = ""
        for line in log.stdout.splitlines():
            if line.startswith("COMMIT "):
                commit = line[len("COMMIT ") :]
                continue
            matched = _VERSION_FILE.match(Path(line).name)
            if matched is not None:
                sequence.append((int(matched.group(2)), int(matched.group(3)), commit))
        return sequence
    return None


def test_patch_number_never_exceeds_ten() -> None:
    """「逢十进一」：同一条线第三位最大 10，不许出现 `.11`。"""
    problems = _patch_ceiling_problems(_all_version_numbers())
    assert not problems, (
        "补丁号没有逢十进一：\n" + "\n".join(problems) + "\n见 docs/harness/changelog.md §1.1。"
    )


def test_new_minor_is_created_in_order() -> None:
    """次版本下号必须在创建那一刻取「当前最大 + 1」（PIT-026 的机器化）。"""
    sequence = _branch_changelog_order()
    if sequence is None:
        pytest.skip("取不到 changelog 基线引用（浅克隆？），无法复原提交顺序——CI 用 fetch-depth: 0 才会真跑")
    if not sequence:
        pytest.skip("本分支没有新增 changelog 文件")
    problems = _minor_order_problems(sequence)
    assert not problems, (
        "次版本下号顺序有问题：\n" + "\n".join(problems) + "\n见 docs/harness/changelog.md §1.2。"
    )


def test_guards_catch_the_two_documented_pitfalls() -> None:
    """两个守卫对**真实踩过的坑**必须变红（护栏自证：不会红的护栏等于没装）。"""
    # 坑① PIT-026：v27.26.3 之后直接写 v27.28.0，v27.27 缺席
    pit026 = [(26, 3, "c1"), (28, 0, "c2"), (27, 0, "c3")]
    assert _minor_order_problems(pit026) == [], "v27.28 早于生效点，属存量豁免，不该报"
    pit026_live = [(33, 1, "c1"), (35, 0, "c2")]
    live = _minor_order_problems(pit026_live)
    assert live and "跳过了 v27.34" in live[0], live

    # 坑①' 同一条线补丁号倒退：先提交 v27.28.5，又提交 v27.28.3
    backwards = [(28, 5, "c1"), (28, 3, "c2")]
    back = _minor_order_problems(backwards)
    assert back and "必须按提交顺序递增" in back[0], back

    # 坑② 逢十进一：v27.21.10 合法，v27.21.11 违规
    assert _patch_ceiling_problems([(27, 21, 10)]) == []
    over = _patch_ceiling_problems([(27, 21, 11)])
    assert over and "该进位了" in over[0], over
    # 存量豁免：v27.7 的历史超限文件不报
    assert _patch_ceiling_problems([(27, 7, 25)]) == []
