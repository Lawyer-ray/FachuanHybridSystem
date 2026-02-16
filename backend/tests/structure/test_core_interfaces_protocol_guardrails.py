from pathlib import Path


def test_interfaces_does_not_define_protocols_inline():
    """
    测试 interfaces 包的结构：Protocols 应该在独立的协议文件中定义
    """
    root = Path(__file__).resolve().parents[2]
    interfaces_dir = root / "apps" / "core" / "interfaces"
    
    # 确认 interfaces 是一个包（目录）
    assert interfaces_dir.is_dir(), "interfaces 应该是一个包（目录）"
    
    # 确认协议文件存在
    protocol_files = [
        "case_protocols.py",
        "contract_protocols.py", 
        "document_protocols.py",
        "automation_protocols.py",
        "organization_protocols.py"
    ]
    
    for protocol_file in protocol_files:
        file_path = interfaces_dir / protocol_file
        assert file_path.exists(), f"{protocol_file} 应该存在"
    
    # 确认 __init__.py 不包含 Protocol 定义（只应该 re-export）
    init_py = interfaces_dir / "__init__.py"
    assert init_py.exists()
    init_content = init_py.read_text(encoding="utf-8")
    
    # __init__.py 应该只包含 import 语句，不应该定义 Protocol
    lines_with_protocol = [line for line in init_content.split('\n') if '(Protocol)' in line and 'class' in line]
    assert len(lines_with_protocol) == 0, "__init__.py 不应该包含 Protocol 类定义"
