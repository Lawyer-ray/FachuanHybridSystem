"""
Property-Based Tests for Admin File Organization

Feature: backend-structure-optimization, Property 6: Admin 文件组织规范
Validates: Requirements 6.2
"""

import pytest
from apps.core.path import Path
from hypothesis import given, strategies as st, assume


# 定义所有 Django app（排除 core 和 tests）
DJANGO_APPS = [
    'automation',
    'cases',
    'client',
    'contracts',
    'organization'
]

def _has_models(app_path: Path) -> bool:
    models_py = app_path / "models.py"
    if models_py.exists():
        return True
    models_pkg = app_path / "models"
    return models_pkg.exists() and (models_pkg / "__init__.py").exists()


@pytest.mark.property_test
def test_admin_directory_exists():
    """
    Property 6: Admin 文件组织规范
    
    For any Django app with admin configurations, the admin/ directory 
    should exist and contain files named after the models they configure
    
    Validates: Requirements 6.2
    """
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"
    
    errors = []
    
    for app_name in DJANGO_APPS:
        app_path = apps_path / app_name
        
        # 检查 app 是否存在
        if not app_path.exists():
            errors.append(f"App {app_name} does not exist")
            continue
        
        # 有模型才需要 admin
        if not _has_models(app_path):
            continue
        
        # 检查 admin/ 目录是否存在
        admin_dir = app_path / "admin"
        if not admin_dir.exists():
            errors.append(f"App {app_name} missing admin/ directory")
            continue
        
        # 检查 admin/ 目录是否有 __init__.py
        admin_init = admin_dir / "__init__.py"
        if not admin_init.exists():
            errors.append(f"App {app_name} admin/ directory missing __init__.py")
        
        # 检查是否有 admin 文件（至少一个 *_admin.py）
        admin_files = list(admin_dir.glob("*_admin.py"))
        if len(admin_files) == 0:
            errors.append(f"App {app_name} admin/ directory has no *_admin.py files")
    
    assert len(errors) == 0, f"Admin organization validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_admin_files_follow_naming_convention():
    """
    Property 6: Admin 文件命名规范
    
    For any admin file in the admin/ directory, it should follow the 
    naming convention: [model_name]_admin.py
    
    Validates: Requirements 6.2
    """
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"
    
    errors = []
    
    for app_name in DJANGO_APPS:
        app_path = apps_path / app_name
        admin_dir = app_path / "admin"
        
        if not admin_dir.exists():
            continue
        
        # 检查所有 Python 文件
        for py_file in admin_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            
            # 检查文件名是否以 _admin.py 结尾
            if not py_file.name.endswith("_admin.py"):
                errors.append(
                    f"App {app_name}: admin file {py_file.name} does not follow "
                    f"naming convention (*_admin.py)"
                )
    
    assert len(errors) == 0, f"Admin file naming validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_root_admin_py_is_import_only():
    """
    Property 6: 根目录 admin.py 只用于导入
    
    For any Django app, if it has a root admin.py file, it should only 
    contain imports from the admin/ subdirectory
    
    Validates: Requirements 6.2
    """
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"
    
    errors = []
    
    for app_name in DJANGO_APPS:
        app_path = apps_path / app_name
        root_admin = app_path / "admin.py"
        
        if not root_admin.exists():
            continue
        
        # 读取文件内容
        content = root_admin.read_text()
        
        # 检查是否包含 @admin.register 装饰器（不应该有）
        if "@admin.register" in content:
            errors.append(
                f"App {app_name}: root admin.py contains @admin.register decorator. "
                f"Admin classes should be in admin/ subdirectory"
            )
        
        # 检查是否包含 class XXXAdmin(admin.ModelAdmin) 定义（不应该有）
        if "class " in content and "Admin(" in content:
            # 排除导入语句
            lines = content.split("\n")
            for line in lines:
                if line.strip().startswith("class ") and "Admin(" in line and "import" not in line:
                    errors.append(
                        f"App {app_name}: root admin.py contains Admin class definition. "
                        f"Admin classes should be in admin/ subdirectory"
                    )
                    break
    
    assert len(errors) == 0, f"Root admin.py validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


@given(st.sampled_from(DJANGO_APPS))
@pytest.mark.property_test
def test_admin_directory_structure_property(app_name):
    """
    Property 6: Admin 目录结构一致性
    
    For any Django app, the admin/ directory should have a consistent structure:
    - admin/__init__.py exists
    - admin/*_admin.py files exist
    - root admin.py (if exists) only imports from admin/
    
    Validates: Requirements 6.2
    """
    backend_path = Path(__file__).parent.parent.parent
    app_path = backend_path / "apps" / app_name
    
    # 假设 app 存在
    assume(app_path.exists())
    
    assume(_has_models(app_path))
    
    admin_dir = app_path / "admin"
    
    # 验证 admin/ 目录存在
    assert admin_dir.exists(), f"App {app_name} missing admin/ directory"
    
    # 验证 admin/__init__.py 存在
    admin_init = admin_dir / "__init__.py"
    assert admin_init.exists(), f"App {app_name} admin/ directory missing __init__.py"
    
    # 验证至少有一个 *_admin.py 文件
    admin_files = list(admin_dir.glob("*_admin.py"))
    assert len(admin_files) > 0, f"App {app_name} admin/ directory has no *_admin.py files"
