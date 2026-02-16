#!/usr/bin/env python3
"""
Targeted fixes for specific mypy error patterns in services layer.
Focuses on the most common fixable errors.
"""

import re
from pathlib import Path
from typing import List, Tuple


def add_typing_imports(content: str, needed: List[str]) -> str:
    """Add missing typing imports."""
    lines = content.split("\n")

    # Find existing typing import
    typing_line_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            typing_line_idx = i
            break

    if typing_line_idx >= 0:
        # Add to existing import
        existing = lines[typing_line_idx]
        for item in needed:
            if item not in existing:
                existing = existing.rstrip() + f", {item}"
        lines[typing_line_idx] = existing
    else:
        # Add new import after other imports
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_idx = i + 1
            elif line.strip() and not line.startswith("#"):
                break

        if needed:
            lines.insert(insert_idx, f"from typing import {', '.join(needed)}")

    return "\n".join(lines)


def fix_file(file_path: Path) -> Tuple[bool, List[str]]:
    """Fix a single file and return (modified, changes)."""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content
        changes = []
        needed_imports = set()

        lines = content.split("\n")

        # Pattern 1: Functions with -> None that return values
        for i, line in enumerate(lines):
            if "def " in line and "-> None:" in line:
                # Look ahead for return statements
                func_indent = len(line) - len(line.lstrip())
                has_return_value = False

                for j in range(i + 1, min(i + 50, len(lines))):
                    next_line = lines[j]
                    if not next_line.strip():
                        continue

                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_line.strip() and next_indent <= func_indent:
                        break

                    if "return " in next_line:
                        return_part = next_line.split("return", 1)[1].strip()
                        if return_part and return_part != "None":
                            has_return_value = True
                            break

                if has_return_value:
                    lines[i] = line.replace("-> None:", ":")
                    changes.append(f"Removed incorrect -> None from {line.strip()[:50]}")

        # Pattern 2: Add Any type to untyped parameters (simple cases)
        for i, line in enumerate(lines):
            if "def " in line and "(self, " in line and "-> " in line:
                # Check for untyped params
                match = re.search(r"def\s+\w+\s*\(([^)]+)\)", line)
                if match:
                    params = match.group(1)
                    param_list = [p.strip() for p in params.split(",")]

                    new_params = []
                    modified = False

                    for param in param_list:
                        if param in ["self", "cls"]:
                            new_params.append(param)
                        elif ":" not in param:
                            # Untyped param
                            if "=" in param:
                                name, default = param.split("=", 1)
                                new_params.append(f"{name.strip()}: Any = {default.strip()}")
                            else:
                                new_params.append(f"{param}: Any")
                            modified = True
                            needed_imports.add("Any")
                        else:
                            new_params.append(param)

                    if modified:
                        new_signature = ", ".join(new_params)
                        lines[i] = line.replace(f"({params})", f"({new_signature})")
                        changes.append(f"Added Any types to params in {line.strip()[:50]}")

        # Pattern 3: Functions that can return None but type doesn't reflect it
        for i, line in enumerate(lines):
            if "def " in line and "-> " in line and "Optional" not in line:
                match = re.search(r"->\s*([^:]+):", line)
                if match:
                    return_type = match.group(1).strip()
                    if return_type not in ["None", "Any", "NoReturn"]:
                        # Check if function returns None
                        func_indent = len(line) - len(line.lstrip())
                        returns_none = False

                        for j in range(i + 1, min(i + 50, len(lines))):
                            next_line = lines[j]
                            if not next_line.strip():
                                continue

                            next_indent = len(next_line) - len(next_line.lstrip())
                            if next_line.strip() and next_indent <= func_indent:
                                break

                            if next_line.strip() in ["return None", "return"]:
                                returns_none = True
                                break

                        if returns_none:
                            new_return_type = f"Optional[{return_type}]"
                            lines[i] = line.replace(f"-> {return_type}:", f"-> {new_return_type}:")
                            changes.append(f"Changed return type to Optional in {line.strip()[:50]}")
                            needed_imports.add("Optional")

        # Pattern 4: Add return types to simple functions
        for i, line in enumerate(lines):
            if "def " in line and "-> " not in line and ":" in line:
                # Skip special methods
                if any(x in line for x in ["__init__", "__str__", "__repr__", "__eq__"]):
                    continue

                # Check what function returns
                func_indent = len(line) - len(line.lstrip())
                return_values = []

                for j in range(i + 1, min(i + 30, len(lines))):
                    next_line = lines[j]
                    if not next_line.strip():
                        continue

                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_line.strip() and next_indent <= func_indent:
                        break

                    if "return " in next_line:
                        return_part = next_line.split("return", 1)[1].strip()
                        return_values.append(return_part)

                # Determine return type
                if not return_values:
                    continue
                elif all(v in ["", "None"] for v in return_values):
                    return_type = "-> None"
                elif all(v in ["True", "False"] for v in return_values if v):
                    return_type = "-> bool"
                elif len(return_values) == 1 and return_values[0].startswith('"'):
                    return_type = "-> str"
                else:
                    return_type = "-> Any"
                    needed_imports.add("Any")

                # Add return type
                if ")" in line and ":" in line:
                    lines[i] = line.replace("):", f") {return_type}:")
                    changes.append(f"Added {return_type} to {line.strip()[:50]}")

        # Reconstruct content
        content = "\n".join(lines)

        # Add needed imports
        if needed_imports:
            content = add_typing_imports(content, sorted(needed_imports))

        # Write if modified
        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return True, changes

        return False, []

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False, []


def main():
    """Main execution."""
    print("=" * 80)
    print("Targeted fixes for services layer mypy errors")
    print("=" * 80)

    # Find all service files
    services_dir = Path(__file__).parent / "apps"
    service_files = []

    for app_dir in services_dir.iterdir():
        if app_dir.is_dir() and not app_dir.name.startswith("."):
            services_path = app_dir / "services"
            if services_path.exists():
                for py_file in services_path.rglob("*.py"):
                    if py_file.name != "__init__.py":
                        service_files.append(py_file)

    print(f"\nFound {len(service_files)} service files to process\n")

    # Process files
    modified_count = 0
    total_changes = 0

    for file_path in sorted(service_files):
        modified, changes = fix_file(file_path)

        if modified:
            modified_count += 1
            total_changes += len(changes)
            rel_path = file_path.relative_to(Path(__file__).parent)
            print(f"\n✓ {rel_path}")
            for change in changes[:3]:  # Show first 3 changes
                print(f"  - {change}")
            if len(changes) > 3:
                print(f"  ... and {len(changes) - 3} more changes")

    print(f"\n{'=' * 80}")
    print(f"Summary:")
    print(f"  Modified files: {modified_count}")
    print(f"  Total changes: {total_changes}")
    print(f"{'=' * 80}")

    print("\nNext steps:")
    print("1. Run: python3 -m mypy --config-file mypy.ini apps/*/services/ | grep 'Found'")
    print("2. Check for syntax errors: python3 -m py_compile apps/*/services/**/*.py")
    print("3. Run tests: pytest tests/ -x")


if __name__ == "__main__":
    main()
