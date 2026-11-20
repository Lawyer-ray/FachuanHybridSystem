#!/usr/bin/env python3
"""detect-secrets 只读封装 —— pre-commit 钩子入口（替代上游 `--baseline` 直连用法）。

## 为什么需要它

Yelp/detect-secrets v1.5.0 的 `detect-secrets-hook --baseline FILE` **不是只读用法**。
`detect_secrets/pre_commit_hook.py::main()` 的收尾逻辑是：

    if not args.baseline: return 0
    is_modified = should_update_baseline(args.baseline, scanned_results=secrets, filelist=args.filenames, ...)
    if is_modified:
        baseline.save_to_file(args.baseline, filename=args.baseline_filename)   # ← 原地写回
        stdout.write('The baseline file was updated. ... Please `git add{}`'); return 3  # 上游原文是 print

而 `should_update_baseline()` 会对**基线集合本身**调用 `SecretsCollection.trim(scanned_results, filelist)`：
凡是「本次被扫描到、但这一遍扫描没能复现出同一条 (filename, secret_hash, type)」的条目，**整条删除**。
于是：

- 钩子第一次跑某个基线覆盖的文件时，基线会被静默重排/瘦身；
- 基线里存在「扫描端永远复现不出来」的条目时（典型：`frontend/pnpm-lock.yaml` 的 320 条
  高熵串，它被本仓库的 `exclude` 排除在钩子扫描之外，但只要被扫描到就零命中），这些条目
  会在一次普通运行里被整段删掉；
- 本次 filelist 覆盖了基线里**全部**文件、且一条都没复现时，基线被写成 `"results": {}`。
  实测 2879 行 → 957 行（一次普通运行，删 2006 行）；事故现场是 2896 → 146 行（全空）。
- 退出码 3 被 pre-commit 记为 **Failed**，于是「基线被改写」这件事永远发生在**提交失败路径**上，
  再叠加 pre-commit 的 stash 舞蹈（`git checkout -- .` → 跑钩子 → `git apply` 回补丁），
  被改写后的基线会以*未暂存改动*的形态留在工作区（证据：
  `~/.cache/pre-commit/patch1795135540-21617` 里就是那份 `results: {}` 的 diff）。

基线一旦变成 `results: {}`，**历史豁免全部失效**：下一次提交凡是碰到这些文件的，钩子会把
当年人工审计过、判定为误报的字符串重新当成新密钥报出来（实测 exit 1 + “Potential secrets
about to be committed”），提交从此持续失败。

上游 v1.5.0 **没有** `--no-write` / `--dry-run` / `--slim`(只影响 `scan` 的输出) 之类的只读开关
（见 `detect-secrets-hook --help`），所以只读语义只能由这层封装提供。

## 做法

把真基线复制到临时文件，让钩子对着**副本**读写；真基线全程 byte-identical。
退出码映射：0→0（通过）、3→0（副本被修剪，属于钩子的正常副作用，不再当成失败）、1→1（真的发现新密钥）。

## 用法（由 .pre-commit-config.yaml 调用，一般不用手敲）

    python scripts/detect_secrets_readonly.py <files...>

故意刷新基线行号（人工、且应当 review diff）：

    detect-secrets-hook --baseline backend/.secrets.baseline <files...>   # 上游原味，会写回
    python scripts/detect_secrets_readonly.py --print-refresh-hint          # 只想看提示
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile

BASELINE = os.path.join('backend', '.secrets.baseline')
TAG = '[detect-secrets-readonly]'


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, 'rb') as f:
            return f.read()
    except OSError:
        return b''


def main(argv: list[str] | None = None) -> int:
    filenames = list(sys.argv[1:] if argv is None else argv)
    if not filenames:
        # pre-commit 没给文件名（例如全被 exclude 掉）：无事可做
        return 0

    try:
        from detect_secrets.pre_commit_hook import main as hook_main
    except ImportError as exc:  # pragma: no cover - 环境没装 detect-secrets
        sys.stderr.write(
            f'{TAG} 无法导入 detect_secrets（{exc}）。'
            '该钩子必须在 language: python + additional_dependencies: detect-secrets==1.5.0 的'
            '环境里运行；请检查 .pre-commit-config.yaml。\n'
        )
        return 1

    if not os.path.isfile(BASELINE):
        sys.stderr.write(
            f'{TAG} 警告：{BASELINE} 不存在，退化为「无基线扫描」（所有命中都会报出来）。\n'
        )
        rc = hook_main(filenames)
        return 0 if rc == 3 else rc

    before = _read_bytes(BASELINE)
    fd, tmp_baseline = tempfile.mkstemp(prefix='detect-secrets-baseline-', suffix='.json')
    os.close(fd)
    captured = io.StringIO()
    # 注意：这里不能用 try/finally 做「跑完检查真基线」。finally 里的 return 会把
    # 钩子自身抛出的异常静默吞掉（B012），那会让真正的扫描失败装成成功。
    # 改成「异常原样上抛 + 正常路径统一收尾」：临时副本的清理放在 except 与正常路径两处。
    shutil.copyfile(BASELINE, tmp_baseline)
    try:
        # 钩子会直接往 stdout 打 “Please `git add <临时副本>`”，对用户纯噪声，先兜住
        with contextlib.redirect_stdout(captured):
            rc = hook_main(['--baseline', tmp_baseline, *filenames])
    except BaseException:
        os.unlink(tmp_baseline)
        raise

    after = _read_bytes(BASELINE)
    if after != before:
        # 兜底：真基线被动过就立刻还原（正常路径下永远不会走到这里）
        try:
            with open(BASELINE, 'wb') as f:
                f.write(before)
        except OSError as exc:  # pragma: no cover
            os.unlink(tmp_baseline)
            sys.stderr.write(f'{TAG} 严重：{BASELINE} 被改写且无法还原（{exc}）\n')
            return 1
        os.unlink(tmp_baseline)
        sys.stderr.write(
            f'{TAG} 严重：{BASELINE} 被钩子改写，已自动还原。'
            '这说明只读封装被绕过了，请检查 .pre-commit-config.yaml。\n'
        )
        return 1
    os.unlink(tmp_baseline)

    if rc == 3:
        # 副本被钩子 trim/刷行号，属正常副作用；真基线有意不跟（避免静默删条目）
        sys.stderr.write(
            f'{TAG} 钩子在副本上刷新了基线（真基线有意保持不变）。'
            f'如需人工刷新行号见 docs/harness/backend/infra.md。\n'
        )
        return 0

    if rc != 0:
        # 真的发现了新密钥：把钩子原本的诊断原样转给用户
        out = captured.getvalue()
        if out:
            sys.stdout.write(out)

    return rc


if __name__ == '__main__':
    if sys.argv[1:2] == ['--print-refresh-hint']:
        sys.stdout.write(__doc__ or '')
        raise SystemExit(0)
    raise SystemExit(main())
