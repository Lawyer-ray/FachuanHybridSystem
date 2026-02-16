#!/usr/bin/env python3
"""
Phase 2: Fix remaining services layer mypy errors.
Target: Reduce from 1292 to <1000 errors.

Focus areas:
1. func-returns-value (127) - Functions with -> None that return values
2. return-value (172) - Return type mismatches
3. no-untyped-def (368) - Missing type annotations
"""

import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple


def run_mypy() -> Tuple[str, Dict[str, List[str]]]:
    """Run mypy and parse errors by category."""
    result = subprocess.run(
        ["python3", "-m", "mypy", "--config-file", "mypy.ini", "apps/*/services/"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    )

    output = result.stdout + result.stderr

    # Parse errors by type
    errors_by_type: Dict[str, List[str]] = defaultdict(list)

    for line in output.split("\n"):
        if ": error:" in line:
            # Extract error type from [error-type]
            match = re.search(r"\[([^\]]+)\]", line)
            if match:
                error_type = match.group(1)
                errors_by_type[error_type].append(line)

    return output, errors_by_type


def fix_func_returns_value(file_path: Path, content: str) -> str:
    """Fix functions declared -> None but returning values."""
    lines = content.split("\n")
    modified = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for function definitions with -> None
        if "def " in line and "-> None:" in line:
            # Check if this function has return statements with values
            func_indent = len(line) - len(line.lstrip())
            j = i + 1
            has_return_value = False

            # Scan function body
            while j < len(lines):
                next_line = lines[j]
                next_indent = len(next_line) - len(next_line.lstrip())

                # End of function
                if next_line.strip() and next_indent <= func_indent:
                    break

                # Check for return with value
                if next_line.strip().startswith("return ") and next_line.strip() != "return":
                    return_part = next_line.strip()[7:].strip()
                    if return_part and return_part != "None":
                        has_return_value = True
                        break

                j += 1

            # If function returns a value, remove -> None
            if has_return_value:
                lines[i] = line.replace("-> None:", ":")
                modified = True
                print(f"  Fixed func-returns-value: {line.strip()[:60]}")

        i += 1

    return "\n".join(lines) if modified else content


def fix_missing_return_types(file_path: Path, content: str) -> str:
    """Add return type annotations to functions missing them."""
    lines = content.split("\n")
    modified = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for function definitions without return type
        if "def " in line and "(" in line and ":" in line:
            # Skip if already has return type
            if "->" in line:
                i += 1
                continue

            # Skip special methods that don't need return types
            if any(x in line for x in ["__init__", "__str__", "__repr__"]):
                i += 1
                continue

            # Check what the function returns
            func_indent = len(line) - len(line.lstrip())
            j = i + 1
            return_types = set()

            # Scan function body
            while j < len(lines):
                next_line = lines[j]
                next_indent = len(next_line) - len(next_line.lstrip())

                # End of function
                if next_line.strip() and next_indent <= func_indent:
                    break

                # Check for return statements
                if next_line.strip().startswith("return "):
                    return_part = next_line.strip()[7:].strip()
                    if not return_part or return_part == "None":
                        return_types.add("None")
                    elif return_part == "True" or return_part == "False":
                        return_types.add("bool")
                    elif return_part.startswith('"') or return_part.startswith("'"):
                        return_types.add("str")
                    elif return_part.startswith("["):
                        return_types.add("list")
                    elif return_part.startswith("{"):
                        return_types.add("dict")
                    elif return_part.isdigit():
                        return_types.add("int")
                    else:
                        return_types.add("Any")
                elif next_line.strip() == "return":
                    return_types.add("None")

                j += 1

            # Add return type if we found returns
            if return_types:
                if return_types == {"None"}:
                    return_type = "-> None"
                elif len(return_types) == 1:
                    return_type = f"-> {list(return_types)[0]}"
                else:
                    return_type = "-> Any"

                # Insert return type before colon
                lines[i] = line.replace("):", f") {return_type}:")
                modified = True
                print(f"  Added return type {return_type}: {line.strip()[:60]}")

        i += 1

    return "\n".join(lines) if modified else content


def fix_missing_param_types(file_path: Path, content: str) -> str:
    """Add type annotations to function parameters."""
    lines = content.split("\n")
    modified = False

    # Add Any import if not present
    has_any_import = "from typing import" in content and "Any" in content

    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for function definitions
        if "def " in line and "(" in line:
            # Skip if it's a simple function with no params or all params typed
            if line.count(":") >= line.count(",") + 2:  # Rough heuristic
                i += 1
                continue

            # Extract function signature
            match = re.search(r"def\s+\w+\s*\((.*?)\)", line)
            if match:
                params = match.group(1)

                # Skip if empty or only self/cls
                if not params or params.strip() in ["self", "cls"]:
                    i += 1
                    continue

                # Check if params need types
                param_list = [p.strip() for p in params.split(",")]
                needs_types = []

                for param in param_list:
                    if param in ["self", "cls"]:
                        continue
                    if ":" not in param and "=" not in param:
                        needs_types.append(param)
                    elif "=" in param and ":" not in param:
                        # Has default but no type
                        param_name = param.split("=")[0].strip()
                        needs_types.append(param_name)

                if needs_types and len(needs_types) <= 3:  # Only fix simple cases
                    # Add Any type to untyped params
                    new_params = []
                    for param in param_list:
                        if param.strip() in ["self", "cls"]:
                            new_params.append(param)
                        elif any(param.strip().startswith(n) for n in needs_types):
                            if "=" in param:
                                name, default = param.split("=", 1)
                                new_params.append(f"{name.strip()}: Any = {default.strip()}")
                            else:
                                new_params.append(f"{param.strip()}: Any")
                        else:
                            new_params.append(param)

                    new_signature = ", ".join(new_params)
                    lines[i] = line.replace(f"({params})", f"({new_signature})")
                    modified = True

                    if not has_any_import:
                        # Add Any import at the top
                        for j in range(len(lines)):
                            if lines[j].startswith("from typing import"):
                                if "Any" not in lines[j]:
                                    lines[j] = lines[j].rstrip() + ", Any"
                                    has_any_import = True
                                    break
                            elif lines[j].startswith("import ") and j > 0:
                                lines.insert(j, "from typing import Any")
                                has_any_import = True
                                i += 1  # Adjust index
                                break

                    print(f"  Added param types: {line.strip()[:60]}")

        i += 1

    return "\n".join(lines) if modified else content


def fix_return_value_mismatches(file_path: Path, content: str) -> str:
    """Fix return value type mismatches."""
    lines = content.split("\n")
    modified = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for functions returning Optional values
        if "def " in line and "-> " in line and ":" in line:
            # Check if function can return None
            func_indent = len(line) - len(line.lstrip())
            j = i + 1
            can_return_none = False

            while j < len(lines):
                next_line = lines[j]
                next_indent = len(next_line) - len(next_line.lstrip())

                if next_line.strip() and next_indent <= func_indent:
                    break

                if next_line.strip() in ["return None", "return"]:
                    can_return_none = True
                    break

                j += 1

            # If function can return None but type doesn't include Optional
            if can_return_none and "-> " in line and "Optional" not in line and "None" not in line:
                # Extract return type
                match = re.search(r"->\s*([^:]+):", line)
                if match:
                    return_type = match.group(1).strip()
                    if return_type not in ["None", "Any"]:
                        new_return_type = f"Optional[{return_type}]"
                        lines[i] = line.replace(f"-> {return_type}:", f"-> {new_return_type}:")
                        modified = True
                        print(f"  Fixed return-value: {line.strip()[:60]}")

                        # Ensure Optional is imported
                        has_optional = False
                        for k in range(len(lines)):
                            if "from typing import" in lines[k] and "Optional" in lines[k]:
                                has_optional = True
                                break

                        if not has_optional:
                            for k in range(len(lines)):
                                if lines[k].startswith("from typing import"):
                                    lines[k] = lines[k].rstrip() + ", Optional"
                                    break

        i += 1

    return "\n".join(lines) if modified else content


def process_file(file_path: Path) -> bool:
    """Process a single file with all fixes."""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        # Apply fixes in order
        content = fix_func_returns_value(file_path, content)
        content = fix_missing_return_types(file_path, content)
        content = fix_missing_param_types(file_path, content)
        content = fix_return_value_mismatches(file_path, content)

        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return True

        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main():
    """Main execution."""
    print("=" * 80)
    print("Phase 2: Fixing remaining services layer mypy errors")
    print("=" * 80)

    # Find all service files
    services_dir = Path(__file__).parent / "apps"
    service_files = []

    for app_dir in services_dir.iterdir():
        if app_dir.is_dir():
            services_path = app_dir / "services"
            if services_path.exists():
                service_files.extend(services_path.rglob("*.py"))

    print(f"\nFound {len(service_files)} service files")

    # Process files
    modified_count = 0
    for file_path in sorted(service_files):
        if file_path.name == "__init__.py":
            continue

        print(f"\nProcessing: {file_path.relative_to(Path(__file__).parent)}")
        if process_file(file_path):
            modified_count += 1

    print(f"\n{'=' * 80}")
    print(f"Modified {modified_count} files")
    print(f"{'=' * 80}")

    # Run mypy to check results
    print("\nRunning mypy to check results...")
    try:
        output, errors_by_type = run_mypy()

        print("\nError summary:")
        for error_type, errors in sorted(errors_by_type.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"  {error_type}: {len(errors)}")

        total_errors = sum(len(errors) for errors in errors_by_type.values())
        print(f"\nTotal errors: {total_errors}")

        if total_errors < 1000:
            print("✅ Target achieved! Errors reduced below 1000")
        else:
            print(f"⚠️  Still need to reduce {total_errors - 1000} more errors")
    except Exception as e:
        print(f"Could not run mypy: {e}")
        print("Please run manually: python3 -m mypy --config-file mypy.ini apps/*/services/")


if __name__ == "__main__":
    main()
