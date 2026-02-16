from pathlib import Path


def test_interfaces_does_not_define_dataclass_dtos():
    """
    测试 interfaces 包的结构：DTOs 应该在独立的 dtos.py 文件中定义
    """
    root = Path(__file__).resolve().parents[2]
    interfaces_dir = root / "apps" / "core" / "interfaces"

    # 确认 interfaces 是一个包（目录）
    assert interfaces_dir.is_dir(), "interfaces 应该是一个包（目录）"

    # 确认 DTOs 在 dtos.py 中定义
    dtos_py = interfaces_dir / "dtos.py"
    assert dtos_py.exists(), "dtos.py 应该存在"

    # 确认 __init__.py 不包含 @dataclass 定义（只应该 re-export）
    init_py = interfaces_dir / "__init__.py"
    assert init_py.exists()
    init_content = init_py.read_text(encoding="utf-8")
    assert "@dataclass" not in init_content, "__init__.py 不应该包含 @dataclass 定义"

    # 确认其他协议文件不包含 @dataclass
    for protocol_file in [
        "case_protocols.py",
        "contract_protocols.py",
        "document_protocols.py",
        "automation_protocols.py",
        "organization_protocols.py",
        "service_locator.py",
    ]:
        file_path = interfaces_dir / protocol_file
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            assert "@dataclass" not in content, f"{protocol_file} 不应该包含 @dataclass 定义"
