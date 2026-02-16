#!/usr/bin/env python3
"""
修复 contracts 模块的高级类型错误

主要问题：
1. QuerySet 需要 2 个类型参数：QuerySet[Model, Model]
2. 方法签名不匹配父类（需要使用 **kwargs）
3. Schema 中的类型错误
"""

import re
from pathlib import Path


def fix_queryset_generic(content: str) -> str:
    """修复 QuerySet 泛型参数 - Django 需要 2 个参数"""
    # QuerySet[Model] -> QuerySet[Model, Model]
    pattern = r"QuerySet\[(\w+)\]"
    replacement = r"QuerySet[\1, \1]"
    content = re.sub(pattern, replacement, content)
    return content


def fix_folder_binding_service(file_path: Path) -> bool:
    """修复 folder_binding_service.py 的方法签名"""
    content = file_path.read_text(encoding="utf-8")
    original = content

    # 修复方法签名，添加 **kwargs 以匹配父类
    replacements = [
        # create_binding
        (
            r"def create_binding\(self, contract_id: int, folder_path: str\) -> Any:",
            "def create_binding(self, contract_id: int, folder_path: str, **kwargs: Any) -> Any:",
        ),
        # update_binding
        (
            r"def update_binding\(self, contract_id: int, folder_path: str\) -> Any:",
            "def update_binding(self, contract_id: int, folder_path: str, **kwargs: Any) -> Any:",
        ),
        # delete_binding
        (
            r"def delete_binding\(self, contract_id: int\) -> bool:",
            "def delete_binding(self, contract_id: int, **kwargs: Any) -> bool:",
        ),
        # get_binding
        (
            r"def get_binding\(self, contract_id: int\) -> ContractFolderBinding \| None:",
            "def get_binding(self, contract_id: int, **kwargs: Any) -> ContractFolderBinding | None:",
        ),
        # save_file_to_bound_folder
        (
            r'def save_file_to_bound_folder\(\s*self, contract_id: int, file_content: bytes, file_name: str, subdir_key: str = "contract_documents"\s*\) -> str \| None:',
            'def save_file_to_bound_folder(\n        self, contract_id: int, file_content: bytes, file_name: str, subdir_key: str = "contract_documents", **kwargs: Any\n    ) -> str | None:',
        ),
        # extract_zip_to_bound_folder
        (
            r"def extract_zip_to_bound_folder\(self, contract_id: int, zip_content: bytes\) -> str \| None:",
            "def extract_zip_to_bound_folder(self, contract_id: int, zip_content: bytes, **kwargs: Any) -> str | None:",
        ),
    ]

    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def fix_contract_schemas(file_path: Path) -> bool:
    """修复 contract_schemas.py 的类型错误"""
    content = file_path.read_text(encoding="utf-8")
    original = content

    # 修复 resolve_cases 返回类型
    content = re.sub(
        r"def resolve_cases\(obj: Contract\) -> Any:", "def resolve_cases(obj: Contract) -> list[Any]:", content
    )

    # 修复 resolve_contract_parties 返回类型
    content = re.sub(
        r"def resolve_contract_parties\(obj: Contract\) -> list\[ContractPartyOut\]:",
        "def resolve_contract_parties(obj: Contract) -> list[Any]:",
        content,
    )

    # 修复 resolve_reminders 返回类型
    content = re.sub(
        r"def resolve_reminders\(obj: Contract\) -> Any:", "def resolve_reminders(obj: Contract) -> list[Any]:", content
    )

    # 修复 resolve_payments 返回类型
    content = re.sub(
        r"def resolve_payments\(obj: Contract\) -> Any:", "def resolve_payments(obj: Contract) -> list[Any]:", content
    )

    # 修复 resolve_supplementary_agreements 返回类型
    content = re.sub(
        r"def resolve_supplementary_agreements\(obj: Contract\) -> Any:",
        "def resolve_supplementary_agreements(obj: Contract) -> list[Any]:",
        content,
    )

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def main():
    """主函数"""
    backend_path = Path(__file__).parent.parent
    contracts_path = backend_path / "apps" / "contracts"

    print("修复 contracts 模块的高级类型错误...")

    # 1. 修复所有文件的 QuerySet 泛型
    print("\n1. 修复 QuerySet 泛型参数...")
    fixed_count = 0
    for py_file in contracts_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        content = py_file.read_text(encoding="utf-8")
        original = content
        content = fix_queryset_generic(content)

        if content != original:
            py_file.write_text(content, encoding="utf-8")
            fixed_count += 1
            rel_path = py_file.relative_to(backend_path)
            print(f"  ✓ {rel_path}")

    print(f"  修复了 {fixed_count} 个文件")

    # 2. 修复 folder_binding_service.py
    print("\n2. 修复 folder_binding_service.py 方法签名...")
    folder_binding_file = contracts_path / "services" / "folder" / "folder_binding_service.py"
    if folder_binding_file.exists():
        if fix_folder_binding_service(folder_binding_file):
            print(f"  ✓ {folder_binding_file.relative_to(backend_path)}")
        else:
            print("  无需修复")

    # 3. 修复 contract_schemas.py
    print("\n3. 修复 contract_schemas.py 类型注解...")
    schemas_file = contracts_path / "schemas" / "contract_schemas.py"
    if schemas_file.exists():
        if fix_contract_schemas(schemas_file):
            print(f"  ✓ {schemas_file.relative_to(backend_path)}")
        else:
            print("  无需修复")

    print("\n修复完成！")


if __name__ == "__main__":
    main()
