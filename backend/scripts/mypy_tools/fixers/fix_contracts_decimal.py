#!/usr/bin/env python3
"""
修复 contracts 模块的 Decimal/float 类型错误
"""

from pathlib import Path
import re


def fix_payment_service(file_path: Path) -> bool:
    """修复 contract_payment_service.py 的 Decimal 类型问题"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复 obj.amount = amount (float -> Decimal)
    content = re.sub(
        r'(\s+)obj\.amount = amount\b',
        r'\1obj.amount = Decimal(str(amount))',
        content
    )
    
    # 修复 obj.invoiced_amount = invoiced_amount (float -> Decimal)
    content = re.sub(
        r'(\s+)obj\.invoiced_amount = invoiced_amount\b',
        r'\1obj.invoiced_amount = Decimal(str(invoiced_amount))',
        content
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True
    return False


def main():
    """主函数"""
    backend_path = Path(__file__).parent.parent
    
    print("修复 contracts 模块的 Decimal 类型错误...")
    
    # 修复 contract_payment_service.py
    payment_service_files = [
        backend_path / "apps" / "contracts" / "services" / "contract_payment_service.py",
        backend_path / "apps" / "contracts" / "services" / "payment" / "contract_payment_service.py",
    ]
    
    for file_path in payment_service_files:
        if file_path.exists():
            if fix_payment_service(file_path):
                print(f"✓ {file_path.relative_to(backend_path)}")
            else:
                print(f"  {file_path.relative_to(backend_path)} - 无需修复")
    
    print("\n修复完成！")


if __name__ == "__main__":
    main()
