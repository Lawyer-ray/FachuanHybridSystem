"""
Property-Based Tests for Service File Organization

Feature: backend-structure-optimization, Property 8: Service 文件组织规范
Validates: Requirements 6.4
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


@pytest.mark.property_test
def test_services_directory_exists():
    """
    Property 8: Service 文件组织规范
    
    For any Django app with business logic, the services/ directory should 
    exist and contain files named after the business domains they handle
    
    Validates: Requirements 6.4
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
        
        # 检查 services/ 目录是否存在
        services_dir = app_path / "services"
        if not services_dir.exists():
            errors.append(f"App {app_name} missing services/ directory")
            continue
        
        # 检查 services/ 目录是否有 __init__.py
        services_init = services_dir / "__init__.py"
        if not services_init.exists():
            errors.append(f"App {app_name} services/ directory missing __init__.py")
        
        # 检查是否有 service 文件（至少一个 *_service.py）
        service_files = list(services_dir.glob("*_service.py"))
        if len(service_files) == 0:
            # 对于某些 app，services 可能是子目录结构
            # 检查是否有子目录
            subdirs = [d for d in services_dir.iterdir() if d.is_dir() and not d.name.startswith('__')]
            if len(subdirs) == 0:
                errors.append(f"App {app_name} services/ directory has no *_service.py files or subdirectories")
    
    assert len(errors) == 0, f"Services organization validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_service_files_follow_naming_convention():
    """
    Property 8: Service 文件命名规范
    
    For any service file in the services/ directory, it should follow the 
    naming convention: [domain_name]_service.py or be in a specialized subdirectory
    
    Validates: Requirements 6.4
    """
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"
    
    errors = []
    
    ALLOWED_SPECIAL_FILES = {
        'config.py', 'utils.py', 'exceptions.py', 'base.py',
        'browser_config.py', 'anti_detection.py', 'browser_manager.py',
        'captcha_recognizer.py', 'court_zxfw.py', 'court_document.py',
        'court_filing.py', 'document_processing.py',
        'ollama_client.py', 'moonshot_client.py', 'prompts.py',
        'court_insurance_client.py', 'example_usage.py', 
        'preservation_quote_example.py', 'text_parser.py',
        'test_scraper.py',
        'wiring.py',
        # Token 模块的辅助类文件
        'cache_manager.py',           # 缓存管理器
        'performance_monitor.py',     # 性能监控器
        'history_recorder.py',        # 历史记录器
        'account_selection_strategy.py',  # 账号选择策略
        'concurrency_optimizer.py',   # 并发优化器
        # Insurance 模块的适配器
        'preservation_quote_service_adapter.py',  # 服务适配器
        "schemas.py",
        "schema.py",
        "types.py",
        "constants.py",
        "interfaces.py",
        "registry.py",
        "service_locator.py",
        "factory.py",
        "adapter.py",
        "storage.py",
        "data_classes.py",
    }

    ALLOWED_SUFFIXES = (
        "_service.py",
        "_adapter.py",
        "_client.py",
        "_factory.py",
        "_provider.py",
        "_strategy.py",
        "_manager.py",
        "_monitor.py",
        "_recorder.py",
        "_parser.py",
        "_config.py",
        "_schemas.py",
        "_schema.py",
        "_dto.py",
        "_types.py",
        "_constants.py",
        "_exceptions.py",
        "_utils.py",
        "_helpers.py",
        "_client_adapter.py",
        "_service_adapter.py",
        "_api.py",
        "_builder.py",
        "_logger.py",
        "_stages.py",
        "_stage.py",
        "_parsers.py",
        "_validators.py",
        "_patterns.py",
        "_classifier.py",
        "_extractor.py",
        "_batch.py",
        "_data.py",
        "_download.py",
        "_downloader.py",
        "_processor.py",
        "_coordinator.py",
        "_operations.py",
        "_renamer.py",
        "_matcher.py",
        "_browse.py",
        "_security.py",
        "_inline.py",
        "_dialog.py",
        "_message_builder.py",
        "_mixin.py",
        "_assembler.py",
        "_facade.py",
        "_policy.py",
        "_gateway.py",
        "_workflow.py",
        "_repo.py",
        "_assemblers.py",
    )
    
    for app_name in DJANGO_APPS:
        app_path = apps_path / app_name
        services_dir = app_path / "services"
        
        if not services_dir.exists():
            continue
        
        # 检查所有 Python 文件（递归）
        for py_file in services_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue

            if py_file.parent != services_dir:
                continue
            
            if py_file.name in ALLOWED_SPECIAL_FILES:
                continue

            if py_file.name.startswith("test_") and py_file.name.endswith(".py"):
                continue

            if any(py_file.name.endswith(suffix) for suffix in ALLOWED_SUFFIXES):
                continue

            if py_file.name.endswith(".py"):
                errors.append(
                    f"App {app_name}: Service file {py_file.relative_to(services_dir)} "
                    f"does not follow naming convention (*_service.py or allowed special file)"
                )
    
    assert len(errors) == 0, f"Service file naming validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_service_files_contain_service_class():
    """
    Property 8: Service 文件包含 Service 类
    
    For any service file in the services/ directory (except __init__.py), 
    it should define at least one Service class
    
    Validates: Requirements 6.4
    """
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"
    
    errors = []
    
    for app_name in DJANGO_APPS:
        app_path = apps_path / app_name
        services_dir = app_path / "services"
        
        if not services_dir.exists():
            continue
        
        # 检查所有 *_service.py 文件
        for service_file in services_dir.rglob("*_service.py"):
            content = service_file.read_text()
            
            # 检查是否定义了 Service 类
            if "class " not in content or "Service" not in content:
                errors.append(
                    f"App {app_name}: Service file {service_file.relative_to(services_dir)} "
                    f"does not define a Service class"
                )
    
    assert len(errors) == 0, f"Service class validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_no_root_services_py():
    """
    Property 8: 不应该有根目录 services.py
    
    For any Django app, there should not be a root services.py file.
    All services should be in the services/ subdirectory
    
    Validates: Requirements 6.4
    """
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"
    
    errors = []
    
    for app_name in DJANGO_APPS:
        app_path = apps_path / app_name
        root_services = app_path / "services.py"
        
        if root_services.exists():
            errors.append(
                f"App {app_name}: has root services.py file. "
                f"Services should be in services/ subdirectory"
            )
    
    assert len(errors) == 0, f"Root services.py validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


@given(st.sampled_from(DJANGO_APPS))
@pytest.mark.property_test
def test_services_directory_structure_property(app_name):
    """
    Property 8: Services 目录结构一致性
    
    For any Django app, the services/ directory should have a consistent structure:
    - services/__init__.py exists
    - services/*_service.py files exist (or subdirectories with service files)
    - no root services.py file
    
    Validates: Requirements 6.4
    """
    backend_path = Path(__file__).parent.parent.parent
    app_path = backend_path / "apps" / app_name
    
    # 假设 app 存在
    assume(app_path.exists())
    
    services_dir = app_path / "services"
    
    # 验证 services/ 目录存在
    assert services_dir.exists(), f"App {app_name} missing services/ directory"
    
    # 验证 services/__init__.py 存在
    services_init = services_dir / "__init__.py"
    assert services_init.exists(), f"App {app_name} services/ directory missing __init__.py"
    
    # 验证至少有一个 *_service.py 文件或子目录
    service_files = list(services_dir.glob("*_service.py"))
    subdirs = [d for d in services_dir.iterdir() if d.is_dir() and not d.name.startswith('__')]
    
    assert len(service_files) > 0 or len(subdirs) > 0, (
        f"App {app_name} services/ directory has no *_service.py files or subdirectories"
    )
    
    # 验证没有根目录 services.py
    root_services = app_path / "services.py"
    assert not root_services.exists(), f"App {app_name} should not have root services.py file"
