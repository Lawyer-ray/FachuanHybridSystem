"""Pre-commit / CI guardrails for sensitive patterns and diff-based checks."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

SOURCE_DIR_PREFIXES = (
    "backend/apps/",
    "backend/apiSystem/",
    "backend/scripts/",
    "scripts/",
)
FORBIDDEN_BINARY_EXTENSIONS = (".onnx", ".mp4", ".zip")
FORBIDDEN_PRIVATE_PATH_PREFIXES = (
    "backend/apps/legal_research/services/sources/weike_api_private/",
    "backend/apps/legal_research/services/sources/weike/api_private/",
)
ALLOWLIST_MARKERS = (
    "pragma: allowlist secret",
    "allowlist secret",
    "# nosec",
)
PLACEHOLDER_PATTERN = re.compile(
    r"(?i)(example|sample|dummy|placeholder|changeme|redacted|masked|测试|示例|\*\*\*|xxxx)"
)
CN_ID_PATTERN = re.compile(
    r"\b[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[0-9Xx]\b"
)
SENSITIVE_LITERAL_ASSIGN_PATTERN = re.compile(
    r"(?i)\b(?:password|passwd|pwd|token|access[_-]?token|refresh[_-]?token|api[_-]?key|secret(?:[_-]?key)?|authorization|cookie|sessionid)\b"
    r"\s*[:=]\s*['\"][^'\"]{4,}['\"]"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{12,}\b")
CN_MOBILE_PATTERN = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _run_git(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True)
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def _parse_added_lines(diff_text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    current_line = 0
    for line in diff_text.splitlines():
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            if match:
                current_line = int(match.group(1)) - 1
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current_line += 1
            lines.append((current_line, line[1:]))
            continue
        if line.startswith("-"):
            continue
        current_line += 1
    return lines


def _get_changed_files(mode: str, base: str | None, head: str) -> list[str]:
    if mode == "staged":
        output = _run_git(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    else:
        if not base:
            return []
        output = _run_git(["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}..{head}"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _get_added_lines(filepath: str, mode: str, base: str | None, head: str) -> list[tuple[int, str]]:
    if mode == "staged":
        output = _run_git(["git", "diff", "--cached", "-U0", "--", filepath])
    else:
        if not base:
            return []
        output = _run_git(["git", "diff", f"{base}..{head}", "-U0", "--", filepath])
    return _parse_added_lines(output)


def _resolve_candidates(files: list[str], mode: str, base: str | None, head: str) -> list[str]:
    if files:
        return files
    return _get_changed_files(mode, base, head)


def _check_todo(filepath: str, mode: str, base: str | None, head: str) -> list[str]:
    errors: list[str] = []
    for lineno, content in _get_added_lines(filepath, mode, base, head):
        if "TODO" in content or "FIXME" in content:
            errors.append(f"{filepath}:{lineno}: 新增了 TODO/FIXME 标记")
    return errors


def _check_print(filepath: str, mode: str, base: str | None, head: str) -> list[str]:
    errors: list[str] = []
    try:
        source = Path(filepath).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, OSError, UnicodeDecodeError):
        return errors

    added_linenos = {ln for ln, _ in _get_added_lines(filepath, mode, base, head)}
    if not added_linenos:
        return errors

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in ("print", "pprint") and node.lineno in added_linenos:
                errors.append(f"{filepath}:{node.lineno}: 新增了 {name}() 调用，请改用 logger")
    return errors


def _is_forbidden_binary_path(filepath: str) -> str | None:
    normalized = filepath.replace("\\", "/")
    if not any(normalized.startswith(prefix) for prefix in SOURCE_DIR_PREFIXES):
        return None
    lowered = normalized.lower()
    for ext in FORBIDDEN_BINARY_EXTENSIONS:
        if lowered.endswith(ext):
            return ext
    return None


def _check_binary_ext(files: list[str], mode: str, base: str | None, head: str) -> list[str]:
    errors: list[str] = []
    for filepath in _resolve_candidates(files, mode, base, head):
        ext = _is_forbidden_binary_path(filepath)
        if ext:
            errors.append(f"{filepath}: 禁止在源码目录提交 {ext} 文件，请改用制品仓/对象存储")
    return errors


def _check_private_paths(files: list[str], mode: str, base: str | None, head: str) -> list[str]:
    errors: list[str] = []
    for filepath in _resolve_candidates(files, mode, base, head):
        normalized = filepath.replace('\\', '/').lower()
        if any(normalized.startswith(prefix) for prefix in FORBIDDEN_PRIVATE_PATH_PREFIXES):
            errors.append(f"{filepath}: 禁止提交威科私有实现目录（weike_api_private/api_private）")
    return errors


def _has_allowlist_marker(content: str) -> bool:
    lowered = content.lower()
    return any(marker in lowered for marker in ALLOWLIST_MARKERS)


def _check_sensitive(files: list[str], mode: str, base: str | None, head: str) -> list[str]:
    errors: list[str] = []
    for filepath in _resolve_candidates(files, mode, base, head):
        # 跳过 lock 文件（自动生成，包含大量 URL 和哈希值）
        if filepath.endswith(('.lock', 'uv.lock', 'poetry.lock', 'Pipfile.lock')):
            continue
        for lineno, content in _get_added_lines(filepath, mode, base, head):
            if _has_allowlist_marker(content):
                continue
            if CN_ID_PATTERN.search(content):
                errors.append(f"{filepath}:{lineno}: 检测到疑似身份证号，请脱敏或移除")
                continue
            if CN_MOBILE_PATTERN.search(content):
                if not PLACEHOLDER_PATTERN.search(content):
                    errors.append(f"{filepath}:{lineno}: 检测到疑似手机号，请脱敏或改为占位符")
                    continue
            if EMAIL_PATTERN.search(content):
                if not PLACEHOLDER_PATTERN.search(content):
                    errors.append(f"{filepath}:{lineno}: 检测到疑似邮箱地址，请脱敏或改为占位符")
                    continue
            if BEARER_PATTERN.search(content):
                errors.append(f"{filepath}:{lineno}: 检测到 Bearer Token 字符串，请移除")
                continue
            if SENSITIVE_LITERAL_ASSIGN_PATTERN.search(content):
                if PLACEHOLDER_PATTERN.search(content):
                    continue
                errors.append(f"{filepath}:{lineno}: 检测到密码/Token 关键词字面量赋值，请改为环境变量或密钥管理")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", choices=["todo", "print", "binary-ext", "private-path", "sensitive"], required=True)
    parser.add_argument("--mode", choices=["staged", "range"], default="staged")
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    if args.mode == "range" and not args.base:
        print("--mode range 必须提供 --base", file=sys.stderr)
        sys.exit(2)

    all_errors: list[str] = []
    if args.check == "binary-ext":
        all_errors.extend(_check_binary_ext(args.files, args.mode, args.base, args.head))
    elif args.check == "private-path":
        all_errors.extend(_check_private_paths(args.files, args.mode, args.base, args.head))
    elif args.check == "sensitive":
        all_errors.extend(_check_sensitive(args.files, args.mode, args.base, args.head))
    else:
        for filepath in args.files:
            if args.check == "todo":
                all_errors.extend(_check_todo(filepath, args.mode, args.base, args.head))
            else:
                all_errors.extend(_check_print(filepath, args.mode, args.base, args.head))

    if all_errors:
        for err in all_errors:
            print(err)
        sys.exit(1)


if __name__ == "__main__":
    main()
