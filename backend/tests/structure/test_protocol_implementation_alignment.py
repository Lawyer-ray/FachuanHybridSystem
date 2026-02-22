import ast
from pathlib import Path
from typing import Set


def _get_project_root() -> Path:
    return Path(__file__).parent.parent.parent


def _get_class_method_names(file_path: Path, class_name: str) -> set[str]:
    content = file_path.read_text(encoding="utf-8")
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            names: set[str] = set()
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    names.add(item.name)
            return names
    raise AssertionError(f"Class not found: {class_name} in {file_path}")


def _assert_impl_covers_protocol(proto_file: Path, proto_class: str, impl_file: Path, impl_class: str) -> None:
    proto_methods = _get_class_method_names(proto_file, proto_class)
    impl_methods = _get_class_method_names(impl_file, impl_class)

    missing = sorted(m for m in proto_methods if m not in impl_methods)
    assert not missing, f"{impl_class} missing protocol methods {missing} from {proto_class}"


def test_document_service_adapter_covers_idocumentservice() -> None:
    root = _get_project_root()
    _assert_impl_covers_protocol(
        proto_file=root / "apps" / "core" / "protocols" / "document_protocols.py",
        proto_class="IDocumentService",
        impl_file=root / "apps" / "documents" / "services" / "document_service_adapter.py",
        impl_class="DocumentServiceAdapter",
    )


def test_folder_binding_service_covers_icontractfolderbindingservice() -> None:
    root = _get_project_root()
    _assert_impl_covers_protocol(
        proto_file=root / "apps" / "core" / "protocols" / "contract_protocols.py",
        proto_class="IContractFolderBindingService",
        impl_file=root / "apps" / "contracts" / "services" / "folder" / "folder_binding_service.py",
        impl_class="FolderBindingService",
    )


def test_litigation_fee_calculator_covers_protocol() -> None:
    root = _get_project_root()
    _assert_impl_covers_protocol(
        proto_file=root / "apps" / "core" / "protocols" / "case_protocols.py",
        proto_class="ILitigationFeeCalculatorService",
        impl_file=root / "apps" / "cases" / "services" / "data" / "litigation_fee_calculator_service.py",
        impl_class="LitigationFeeCalculatorService",
    )


def test_organization_service_adapter_covers_protocol() -> None:
    root = _get_project_root()
    _assert_impl_covers_protocol(
        proto_file=root / "apps" / "core" / "protocols" / "organization_protocols.py",
        proto_class="IOrganizationService",
        impl_file=root / "apps" / "organization" / "services" / "organization_service_adapter.py",
        impl_class="OrganizationServiceAdapter",
    )
