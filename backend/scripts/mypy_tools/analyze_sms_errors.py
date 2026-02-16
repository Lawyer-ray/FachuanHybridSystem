#!/usr/bin/env python3
"""Analyze mypy errors in SMS module."""

import re
import subprocess
from collections import defaultdict
from pathlib import Path


def run_mypy_on_sms() -> str:
    """Run mypy on SMS module and return output."""
    result = subprocess.run(
        [".venv/bin/python", "-m", "mypy", "apps/automation/services/sms/", "--strict"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    return result.stdout + result.stderr


def parse_errors(mypy_output: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Parse mypy output into structured errors.

    Returns:
        (sms_errors, other_errors) - SMS module errors and errors from other modules
    """
    sms_errors = []
    other_errors = []
    lines = mypy_output.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]

        if not line.strip() or ": error:" not in line:
            i += 1
            continue

        # Parse error line - match any apps/ path
        # Error format: file:line:col: error: message [code]
        # But message might be on next line
        match = re.match(r"^(apps/[^:]+):(\d+):(\d+): error:\s*(.*)$", line)
        if match:
            file_path, line_no, col_no, message = match.groups()

            # If message is empty or doesn't have error code, check next line
            if not message or "[" not in message:
                i += 1
                if i < len(lines):
                    message = lines[i].strip()

            # Extract error code
            error_code_match = re.search(r"\[([^\]]+)\]", message)
            if error_code_match:
                error_code = error_code_match.group(1)
                # Remove error code from message
                message = re.sub(r"\s*\[([^\]]+)\]\s*$", "", message)
            else:
                error_code = "unknown"

            error = {
                "file": file_path,
                "line": int(line_no),
                "col": int(col_no),
                "message": message,
                "code": error_code,
            }

            # Categorize by module
            if file_path.startswith("apps/automation/services/sms/"):
                sms_errors.append(error)
            else:
                other_errors.append(error)

        i += 1

    return sms_errors, other_errors


def categorize_errors(errors: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Categorize errors by type."""
    categorized = defaultdict(list)

    for error in errors:
        categorized[error["code"]].append(error)

    return dict(categorized)


def print_summary(categorized: dict[str, list[dict[str, str]]]) -> None:
    """Print error summary."""
    total = sum(len(errors) for errors in categorized.values())

    print(f"Total SMS module errors: {total}\n")
    print("Error breakdown by type:")
    print("-" * 60)

    # Sort by count descending
    sorted_categories = sorted(categorized.items(), key=lambda x: len(x[1]), reverse=True)

    for error_code, errors in sorted_categories:
        count = len(errors)
        percentage = (count / total * 100) if total > 0 else 0
        print(f"{error_code:25} {count:4} ({percentage:5.1f}%)")

    print("-" * 60)
    print(f"{'TOTAL':25} {total:4} (100.0%)")


def print_file_breakdown(errors: list[dict[str, str]]) -> None:
    """Print errors by file."""
    by_file = defaultdict(list)

    for error in errors:
        by_file[error["file"]].append(error)

    print("\n\nTop 10 files with most errors:")
    print("-" * 60)

    sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)[:10]

    for file_path, file_errors in sorted_files:
        filename = Path(file_path).name
        count = len(file_errors)
        print(f"{filename:40} {count:4} errors")


def print_simple_type_errors(categorized: dict[str, list[dict[str, str]]]) -> None:
    """Print details of simple type errors that can be batch fixed."""
    print("\n\nSimple type errors (can be batch fixed):")
    print("=" * 60)

    # type-arg errors
    if "type-arg" in categorized:
        print(f"\n[type-arg] Missing generic type parameters: {len(categorized['type-arg'])} errors")
        print("Examples:")
        for error in categorized["type-arg"][:3]:
            print(f"  {Path(error['file']).name}:{error['line']} - {error['message']}")

    # no-untyped-def errors
    if "no-untyped-def" in categorized:
        print(f"\n[no-untyped-def] Functions missing type annotations: {len(categorized['no-untyped-def'])} errors")
        print("Examples:")
        for error in categorized["no-untyped-def"][:3]:
            print(f"  {Path(error['file']).name}:{error['line']} - {error['message']}")

    # assignment errors with None defaults
    if "assignment" in categorized:
        none_defaults = [e for e in categorized["assignment"] if 'default has type "None"' in e["message"]]
        if none_defaults:
            print(f"\n[assignment] Incompatible None defaults: {len(none_defaults)} errors")
            print("Examples:")
            for error in none_defaults[:3]:
                print(f"  {Path(error['file']).name}:{error['line']} - {error['message']}")


def main() -> None:
    """Main function."""
    print("Analyzing SMS module mypy errors...\n")

    mypy_output = run_mypy_on_sms()
    sms_errors, other_errors = parse_errors(mypy_output)

    print(f"SMS module errors: {len(sms_errors)}")
    print(f"Errors from other modules: {len(other_errors)}")
    print(f"Total errors: {len(sms_errors) + len(other_errors)}\n")

    if other_errors:
        print("Errors from other modules (dependencies):")
        other_by_file = defaultdict(int)
        for error in other_errors:
            module = error["file"].split("/")[1]  # Get top-level module
            other_by_file[module] += 1
        for module, count in sorted(other_by_file.items(), key=lambda x: x[1], reverse=True):
            print(f"  apps/{module}: {count} errors")
        print()

    categorized = categorize_errors(sms_errors)

    print_summary(categorized)
    print_file_breakdown(sms_errors)
    print_simple_type_errors(categorized)

    # Save detailed report
    report_path = Path(__file__).parent.parent / "sms_errors_analysis.md"
    with open(report_path, "w") as f:
        f.write("# SMS Module Mypy Errors Analysis\n\n")
        f.write(f"SMS module errors: {len(sms_errors)}\n")
        f.write(f"Errors from other modules: {len(other_errors)}\n")
        f.write(f"Total errors: {len(sms_errors) + len(other_errors)}\n\n")

        if other_errors:
            f.write("## Errors from Other Modules (Dependencies)\n\n")
            other_by_file = defaultdict(int)
            for error in other_errors:
                module = error["file"].split("/")[1]
                other_by_file[module] += 1
            for module, count in sorted(other_by_file.items(), key=lambda x: x[1], reverse=True):
                f.write(f"- apps/{module}: {count} errors\n")
            f.write("\n")

        f.write("## SMS Module Error Breakdown\n\n")

        sorted_categories = sorted(categorized.items(), key=lambda x: len(x[1]), reverse=True)
        for error_code, code_errors in sorted_categories:
            f.write(f"### [{error_code}] - {len(code_errors)} errors\n\n")

            # Group by file
            by_file = defaultdict(list)
            for error in code_errors:
                by_file[error["file"]].append(error)

            for file_path in sorted(by_file.keys()):
                file_errors = by_file[file_path]
                f.write(f"**{Path(file_path).name}** ({len(file_errors)} errors)\n")
                for error in file_errors[:5]:  # Show first 5 per file
                    f.write(f"- Line {error['line']}: {error['message']}\n")
                if len(file_errors) > 5:
                    f.write(f"- ... and {len(file_errors) - 5} more\n")
                f.write("\n")

    print(f"\n\nDetailed report saved to: {report_path}")


if __name__ == "__main__":
    main()
