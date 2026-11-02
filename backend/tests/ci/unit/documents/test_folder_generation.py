"""Tests for FolderGenerationService."""

import zipfile
from datetime import date
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.documents.services.generation.folder_generation_service import DocumentPlacement, FolderGenerationService


class TestDocumentPlacement:
    def test_dataclass(self):
        dp = DocumentPlacement(
            document_template=MagicMock(),
            folder_path="docs/contracts",
            file_name="contract_v1.docx",
        )
        assert dp.folder_path == "docs/contracts"
        assert dp.file_name == "contract_v1.docx"


class TestFolderGenerationService:
    def setup_method(self):
        self.service = FolderGenerationService(
            contract_service=MagicMock(),
            folder_binding_service=MagicMock(),
        )

    def test_init_defaults(self):
        svc = FolderGenerationService()
        assert svc._contract_service is None
        assert svc._folder_binding_service is None

    def test_contract_service_raises_if_not_injected(self):
        svc = FolderGenerationService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.contract_service

    def test_contract_service_returns_injected(self):
        mock_service = MagicMock()
        svc = FolderGenerationService(contract_service=mock_service)
        assert svc.contract_service is mock_service

    def test_folder_binding_service_property(self):
        mock_binding = MagicMock()
        svc = FolderGenerationService(folder_binding_service=mock_binding)
        assert svc.folder_binding_service is mock_binding

    def test_folder_binding_service_none(self):
        svc = FolderGenerationService()
        assert svc.folder_binding_service is None


class TestFormatRootFolderName:
    def setup_method(self):
        self.service = FolderGenerationService(contract_service=MagicMock())

    def test_basic_format(self):
        contract = MagicMock()
        contract.case_type = "civil"
        contract.name = "测试合同"

        from apps.core.models.enums import CaseType

        with patch.dict(dict(CaseType.choices), {"civil": "民商事"}, clear=False):
            result = self.service.format_root_folder_name(contract)

        today = date.today().strftime("%Y.%m.%d")
        assert today in result
        assert "测试合同" in result

    def test_missing_name(self):
        contract = MagicMock()
        contract.case_type = "civil"
        contract.name = None
        result = self.service.format_root_folder_name(contract)
        assert "未命名合同" in result

    def test_missing_case_type(self):
        contract = MagicMock()
        contract.case_type = None
        contract.name = "合同A"
        result = self.service.format_root_folder_name(contract)
        assert "合同A" in result


class TestGenerateFolderStructure:
    def setup_method(self):
        self.service = FolderGenerationService(contract_service=MagicMock())

    def test_template_with_name(self):
        template = MagicMock()
        template.structure = {"name": "old_name", "children": [{"name": "subfolder"}]}

        result = self.service.generate_folder_structure(template, "new_root")
        assert result["name"] == "new_root"
        assert len(result["children"]) == 1

    def test_template_without_name(self):
        template = MagicMock()
        template.structure = {"children": [{"name": "docs"}]}

        result = self.service.generate_folder_structure(template, "new_root")
        assert result["name"] == "new_root"
        assert result["children"][0]["name"] == "docs"

    def test_empty_structure(self):
        template = MagicMock()
        template.structure = {}

        result = self.service.generate_folder_structure(template, "root")
        assert result["name"] == "root"
        assert result["children"] == []

    def test_none_structure(self):
        template = MagicMock()
        template.structure = None

        result = self.service.generate_folder_structure(template, "root")
        assert result["name"] == "root"


class TestFindContractFolderPath:
    def setup_method(self):
        self.service = FolderGenerationService(contract_service=MagicMock())

    def test_find_contract_folder(self):
        template = MagicMock()
        template.structure = {
            "children": [
                {
                    "name": "顾问案件",
                    "children": [
                        {
                            "name": "1-律师资料",
                            "children": [
                                {"name": "1-合同", "children": []},
                            ],
                        },
                    ],
                },
            ]
        }
        result = self.service._find_contract_folder_path(template)
        assert "合同" in result

    def test_no_contract_folder(self):
        template = MagicMock()
        template.structure = {"children": [{"name": "其他", "children": []}]}
        result = self.service._find_contract_folder_path(template)
        assert result == ""

    def test_empty_structure(self):
        template = MagicMock()
        template.structure = {}
        result = self.service._find_contract_folder_path(template)
        assert result == ""


class TestFindFolderByName:
    def setup_method(self):
        self.service = FolderGenerationService(contract_service=MagicMock())

    def test_find_direct(self):
        children = [{"name": "1-合同", "children": []}]
        result = self.service._find_folder_by_name(children, "合同", [])
        assert result == ["1-合同"]

    def test_find_nested(self):
        children = [{"name": "资料", "children": [{"name": "1-合同", "children": []}]}]
        result = self.service._find_folder_by_name(children, "合同", [])
        assert result == ["资料", "1-合同"]

    def test_not_found(self):
        children = [{"name": "其他", "children": []}]
        result = self.service._find_folder_by_name(children, "合同", [])
        assert result == []

    def test_excludes_supplemental(self):
        children = [{"name": "补充协议", "children": []}]
        result = self.service._find_folder_by_name(children, "补充", [])
        assert result == []


class TestFindSpecialFolderPaths:
    def setup_method(self):
        self.service = FolderGenerationService(contract_service=MagicMock())

    def test_finds_identity_folder(self):
        structure = {
            "name": "root",
            "children": [
                {"name": "身份证明材料", "children": []},
                {"name": "委托材料", "children": []},
                {"name": "执行依据及生效证明", "children": []},
            ],
        }
        result = self.service._find_special_folder_paths(structure)
        assert len(result["身份证明"]) == 1
        assert len(result["委托材料"]) == 1
        assert len(result["执行依据及生效证明"]) == 1

    def test_empty_structure(self):
        result = self.service._find_special_folder_paths({})
        assert result["身份证明"] == []
        assert result["委托材料"] == []
        assert result["执行依据及生效证明"] == []

    def test_nested_special_folders(self):
        structure = {
            "name": "root",
            "children": [
                {
                    "name": "子目录",
                    "children": [
                        {"name": "身份证明", "children": []},
                    ],
                },
            ],
        }
        result = self.service._find_special_folder_paths(structure)
        assert len(result["身份证明"]) == 1
        assert "子目录/身份证明" in result["身份证明"][0]


class TestCreateFoldersInZip:
    def setup_method(self):
        self.service = FolderGenerationService(contract_service=MagicMock())

    def test_creates_folders(self):
        import io

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            structure = {
                "name": "root",
                "children": [
                    {"name": "sub1", "children": []},
                    {
                        "name": "sub2",
                        "children": [
                            {"name": "sub2a", "children": []},
                        ],
                    },
                ],
            }
            self.service._create_folders_in_zip(zf, structure, "")

        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer) as zf:
            names = zf.namelist()
            assert "root/" in names
            assert "root/sub1/" in names
            assert "root/sub2/" in names
            assert "root/sub2/sub2a/" in names

    def test_empty_structure(self):
        import io

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            self.service._create_folders_in_zip(zf, {}, "")

        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer) as zf:
            assert len(zf.namelist()) == 0

    def test_no_name_structure(self):
        import io

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            self.service._create_folders_in_zip(zf, {"children": []}, "")

        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer) as zf:
            assert len(zf.namelist()) == 0


class TestExtractToBoundFolder:
    def setup_method(self):
        self.folder_binding_service = MagicMock()
        self.service = FolderGenerationService(
            contract_service=MagicMock(),
            folder_binding_service=self.folder_binding_service,
        )

    def test_calls_binding_service(self):
        self.folder_binding_service.extract_zip_to_bound_folder.return_value = "/extracted/path"
        result = self.service._extract_to_bound_folder_if_exists(1, b"zip_content")
        assert result == "/extracted/path"

    def test_no_binding_service(self):
        svc = FolderGenerationService(contract_service=MagicMock(), folder_binding_service=None)
        result = svc._extract_to_bound_folder_if_exists(1, b"zip")
        assert result is None

    def test_binding_service_exception(self):
        self.folder_binding_service.extract_zip_to_bound_folder.side_effect = Exception("fail")
        result = self.service._extract_to_bound_folder_if_exists(1, b"zip")
        assert result is None

    def test_binding_service_returns_none(self):
        self.folder_binding_service.extract_zip_to_bound_folder.return_value = None
        result = self.service._extract_to_bound_folder_if_exists(1, b"zip")
        assert result is None


class TestGenerateFolderWithDocumentsResult:
    def test_calls_main_method(self):
        service = FolderGenerationService(contract_service=MagicMock())
        service.generate_folder_with_documents = MagicMock(return_value=(b"zip", "test.zip", None))
        service._last_extract_path = "/extracted"

        zip_content, filename, extract_path, error = service.generate_folder_with_documents_result(1)
        assert zip_content == b"zip"
        assert filename == "test.zip"
        assert extract_path == "/extracted"
        assert error is None


class TestSpecialRendererDispatchContract:
    """特殊渲染器与 dispatch 调用点的签名契约。

    回归背景（真实 500）：`_render_legal_rep_certificate` 曾多声明一个
    `failed_templates` 必填参数，而 `generate_case_folder_with_documents` 的
    dispatch 统一按「case/template/file_location/folder_path/documents」五参数
    调用 → `TypeError: missing 1 required positional argument: 'failed_templates'`
    → 整个「生成案件文件夹」接口 500（案件 487 触发）。

    这类 bug 编译器与 mypy 都拦不住（handler 是 `Any` 的动态 getattr），
    所以用反射把「dispatch 的实际调用形状」固化成契约：任何特殊渲染器只要
    签名与之不符，测试立刻失败，而不是等到线上点按钮。
    """

    #: dispatch 处实际传入的关键字参数（与 folder_generation_service 保持一致）
    DISPATCH_KWARGS = ("case", "template", "file_location", "folder_path", "documents")

    def _handlers(self):
        svc = FolderGenerationService()
        return [
            (keyword, method_name, getattr(svc, method_name))
            for keyword, method_name in FolderGenerationService._SPECIAL_RENDERERS
        ]

    def test_every_special_renderer_accepts_dispatch_kwargs(self):
        import inspect

        for keyword, method_name, handler in self._handlers():
            sig = inspect.signature(handler)
            # 去掉 self（getattr 绑定到实例后已经没有 self）
            accepted = [
                name for name, p in sig.parameters.items() if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
            ]
            for kwarg in self.DISPATCH_KWARGS:
                assert kwarg in accepted, (
                    f"{method_name}（匹配词「{keyword}」）缺少 dispatch 传入的参数 {kwarg!r}，"
                    f"实际签名: {list(sig.parameters)}"
                )

    def test_no_special_renderer_requires_extra_positional_args(self):
        """除 dispatch 五参数外，不允许再有必填位置参数（否则调用必然 TypeError）。"""
        import inspect

        for _keyword, method_name, handler in self._handlers():
            sig = inspect.signature(handler)
            required_extra = [
                name
                for name, p in sig.parameters.items()
                if p.default is inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                and name not in self.DISPATCH_KWARGS
            ]
            assert not required_extra, (
                f"{method_name} 有 dispatch 未提供的必填参数 {required_extra}，"
                "调用时会抛 TypeError（正是案件 487 的 500 根因）"
            )

    @pytest.mark.parametrize("keyword,method_name", FolderGenerationService._SPECIAL_RENDERERS)
    def test_handler_callable_with_dispatch_args(self, keyword, method_name):
        """把 dispatch 的真实调用形状打到真 handler 上，不抛 TypeError 即通过。

        这是对上面两条反射契约的运行时兜底：反射看的是签名文本，这里看的是
        Python 真的能把五参数递进去。handler 体内部依赖 DB/渲染，所以用
        MagicMock 让「我方法人」查询返回空 → handler 提前 return，正好只验证
        调用边界这一件事（案件 487 崩在边界上，不是崩在渲染里）。
        """
        svc = FolderGenerationService()
        handler = getattr(svc, method_name)

        case = MagicMock()
        case.id = 1
        empty = []
        case.parties.select_related.return_value.filter.return_value.select_related.return_value = empty
        case.parties.select_related.return_value.all.return_value = empty

        documents: list[tuple[str, bytes, str]] = []
        # 不 expect 异常：缺参数会直接 TypeError
        handler(
            case=case,
            template=MagicMock(name=keyword),
            file_location="/tmp/x.docx",
            folder_path="一审/1-立案材料/3-委托材料",
            documents=documents,
        )
        assert documents == []
