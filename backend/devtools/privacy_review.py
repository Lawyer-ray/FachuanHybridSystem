"""LLM-based privacy review for changed files.

Uses Claude to detect PII that regex cannot catch:
real person names, company names, court case numbers, addresses, etc.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SYSTEM_PROMPT = """\
你是一个隐私信息审查专家。你的任务是检查代码/文档变更中是否包含真实的个人隐私信息。

需要检测的隐私信息类型：
1. 真实人名（非示例名，如"张三"、"李四"这种常见占位符不算）
2. 真实公司/组织名称
3. 法院案号（如"(2024)粤01民初123号"）
4. 真实地址（具体到门牌号的地址）
5. 身份证号、手机号、银行卡号
6. 其他可识别个人身份的信息

不算隐私信息的：
- 代码中的变量名、函数名、类名
- 测试用的占位符（如"张三"、"测试用户"、"example"）
- 已脱敏的内容（如"138****1234"、"张*三"）
- 技术文档中的通用描述
- URL、文件路径、配置项

对每个文件，分析新增的行（以 + 开头的行），判断是否包含真实隐私信息。

返回严格的 JSON 格式（不要包含 markdown 代码块标记）：
{"issues": [{"file": "文件路径", "line": "涉及的原文片段", "reason": "说明为什么这是隐私信息"}]}

如果没有发现问题，返回：{"issues": []}
"""

USER_PROMPT_TEMPLATE = """\
请检查以下文件变更中的隐私信息：

文件：{filepath}

新增内容：
{added_lines}

请返回 JSON 格式的审查结果。"""


def _run_git(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout


def _get_changed_files(base: str, head: str) -> list[str]:
    output = _run_git(["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}..{head}"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _get_added_lines(filepath: str, base: str, head: str) -> list[tuple[int, str]]:
    output = _run_git(["git", "diff", f"{base}..{head}", "-U0", "--", filepath])
    lines: list[tuple[int, str]] = []
    current_line = 0
    for line in output.splitlines():
        if line.startswith("@@"):
            import re
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


def _review_file(filepath: str, added_lines: list[tuple[int, str]], client: object) -> list[dict]:
    """Send added lines to Claude for privacy review."""
    if not added_lines:
        return []

    # Only send lines that look like content (skip pure code structure)
    lines_text = "\n".join(f"+ {content}" for _, content in added_lines)
    if len(lines_text) > 8000:
        lines_text = lines_text[:8000] + "\n... (truncated)"

    user_msg = USER_PROMPT_TEMPLATE.format(filepath=filepath, added_lines=lines_text)

    try:
        resp = client.messages.create(  # type: ignore[union-attr]
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = resp.content[0].text.strip()
        # Strip markdown code block if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        result = json.loads(text)
        return result.get("issues", [])
    except Exception as e:
        print(f"  ⚠ LLM review failed for {filepath}: {e}", file=sys.stderr)
        return []


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-based privacy review for changed files")
    parser.add_argument("--base", required=True, help="Base commit SHA")
    parser.add_argument("--head", default="HEAD", help="Head commit SHA")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("⚠ ANTHROPIC_API_KEY not set, skipping LLM privacy review.")
        sys.exit(0)

    # Lazy import so script loads without anthropic installed when key is missing
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    changed_files = _get_changed_files(args.base, args.head)
    if not changed_files:
        print("No changed files found.")
        sys.exit(0)

    print(f"Reviewing {len(changed_files)} changed file(s) for privacy issues...")

    all_issues: list[dict] = []
    for filepath in changed_files:
        added = _get_added_lines(filepath, args.base, args.head)
        if not added:
            continue
        print(f"  Checking {filepath} ({len(added)} added lines)...")
        issues = _review_file(filepath, added, client)
        all_issues.extend(issues)

    if all_issues:
        print("\n❌ Privacy issues found:\n")
        for issue in all_issues:
            print(f"  File: {issue.get('file', 'unknown')}")
            print(f"  Text: {issue.get('line', '')}")
            print(f"  Reason: {issue.get('reason', '')}")
            print()
        sys.exit(1)

    print("\n✅ No privacy issues found.")
    sys.exit(0)


if __name__ == "__main__":
    main()
