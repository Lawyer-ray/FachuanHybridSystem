"""DocumentParserService 单元测试 — 文书当事人提取与文书路径获取。

mock 客户/律师服务与文书处理适配器，不触碰真实文档与外部服务。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from apps.automation.services.sms.matching.document_parser_service import (
    DocumentParserService,
    _get_document_parser_service,
)


def _client(name: str) -> Any:
    return SimpleNamespace(name=name)


class TestLazyServiceProperties:
    def test_client_service_lazy_build(self) -> None:
        svc = DocumentParserService()
        built = MagicMock()
        with patch("apps.core.dependencies.business_client.build_client_service", return_value=built):
            assert svc.client_service is built
            # 二次访问不再构建
            assert svc.client_service is built

    def test_lawyer_service_lazy_build(self) -> None:
        svc = DocumentParserService()
        built = MagicMock()
        with patch("apps.core.dependencies.business_organization.build_lawyer_service", return_value=built):
            assert svc.lawyer_service is built
            assert svc.lawyer_service is built

    def test_injected_services_kept(self) -> None:
        client = MagicMock()
        lawyer = MagicMock()
        svc = DocumentParserService(client_service=client, lawyer_service=lawyer)
        assert svc.client_service is client
        assert svc.lawyer_service is lawyer

    def test_factory_returns_instance(self) -> None:
        assert isinstance(_get_document_parser_service(), DocumentParserService)


class TestExtractPartiesFromDocument:
    def _doc_service(self, text: str) -> MagicMock:
        service = MagicMock()
        service.extract_document_content_by_path_internal.return_value = {"text": text}
        return service

    def test_matches_clients_in_content(self) -> None:
        doc_service = self._doc_service("原告张三诉被告李四合同纠纷一案")
        parser = DocumentParserService(
            client_service=MagicMock(
                get_all_clients_internal=lambda: [_client("张三"), _client("王五"), _client("赵六")]
            ),
            lawyer_service=MagicMock(get_all_lawyer_names=lambda: []),
        )
        with patch(
            "apps.core.dependencies.automation_adapters.build_document_processing_service", return_value=doc_service
        ):
            result = parser.extract_parties_from_document("/tmp/doc.pdf")

        assert result == ["张三"]
        doc_service.extract_document_content_by_path_internal.assert_called_once_with("/tmp/doc.pdf", limit=3000)

    def test_newlines_removed_before_matching(self) -> None:
        parser = DocumentParserService(
            client_service=MagicMock(get_all_clients_internal=lambda: [_client("佛山市某某公司")]),
            lawyer_service=MagicMock(get_all_lawyer_names=lambda: []),
        )
        doc_service = MagicMock()
        doc_service.extract_document_content_by_path_internal.return_value = {
            "text": "被申请人：\n佛山市某某公司\n（2024）…"
        }
        with patch(
            "apps.core.dependencies.automation_adapters.build_document_processing_service", return_value=doc_service
        ):
            assert parser.extract_parties_from_document("/tmp/x.pdf") == ["佛山市某某公司"]

    def test_empty_text_returns_empty(self) -> None:
        doc_service = MagicMock()
        doc_service.extract_document_content_by_path_internal.return_value = {"text": ""}
        parser = DocumentParserService(client_service=MagicMock(), lawyer_service=MagicMock())
        with patch(
            "apps.core.dependencies.automation_adapters.build_document_processing_service", return_value=doc_service
        ):
            assert parser.extract_parties_from_document("/tmp/x.pdf") == []

    def test_exception_returns_empty(self) -> None:
        parser = DocumentParserService(client_service=MagicMock(), lawyer_service=MagicMock())
        with patch(
            "apps.core.dependencies.automation_adapters.build_document_processing_service",
            side_effect=RuntimeError("挂了"),
        ):
            assert parser.extract_parties_from_document("/tmp/x.pdf") == []


class TestMatchPartiesFromContent:
    def _parser(self, clients: list[Any], lawyers: list[str]) -> DocumentParserService:
        return DocumentParserService(
            client_service=MagicMock(get_all_clients_internal=lambda: clients),
            lawyer_service=MagicMock(get_all_lawyer_names=lambda: lawyers),
        )

    def test_empty_content_returns_empty(self) -> None:
        assert self._parser([_client("张三")], []).match_parties_from_content("") == []

    def test_excludes_lawyers_and_short_names(self) -> None:
        parser = self._parser(
            [_client("张三"), _client("李律师"), _client("王")],  # 李律师被排除、王姓单字太短
            lawyers=["李律师"],
        )
        result = parser.match_parties_from_content("张三与王五纠纷，李律师代理")
        assert result == ["张三"]

    def test_no_match_returns_empty(self) -> None:
        parser = self._parser([_client("钱七")], [])
        assert parser.match_parties_from_content("完全无关内容") == []

    def test_client_service_failure_returns_empty(self) -> None:
        parser = DocumentParserService(
            client_service=MagicMock(get_all_clients_internal=MagicMock(side_effect=RuntimeError("db"))),
            lawyer_service=MagicMock(get_all_lawyer_names=lambda: []),
        )
        assert parser.match_parties_from_content("内容") == []


class TestGetAllDocumentPaths:
    def _sms(self, scraper_task: Any) -> Any:
        return SimpleNamespace(scraper_task=scraper_task)

    def test_collects_existing_paths_from_documents(self, tmp_path) -> None:
        good = tmp_path / "good.pdf"
        good.write_bytes(b"1")
        doc1 = SimpleNamespace(local_file_path=str(good))
        doc2 = SimpleNamespace(local_file_path=str(tmp_path / "missing.pdf"))
        task = MagicMock()
        task.documents.filter.return_value = [doc1, doc2]

        result = DocumentParserService().get_all_document_paths(self._sms(task))

        assert result == [str(good)]

    def test_falls_back_to_task_result_files(self, tmp_path) -> None:
        f1 = tmp_path / "a.pdf"
        f1.write_bytes(b"1")
        task = MagicMock()
        task.documents.filter.return_value = []
        task.result = {"files": [str(f1), str(tmp_path / "gone.pdf")]}

        result = DocumentParserService().get_all_document_paths(self._sms(task))

        assert result == [str(f1)]

    def test_no_scraper_task_returns_empty(self) -> None:
        assert DocumentParserService().get_all_document_paths(self._sms(None)) == []

    def test_exception_returns_empty(self) -> None:
        task = MagicMock()
        task.documents.filter.side_effect = RuntimeError("boom")
        assert DocumentParserService().get_all_document_paths(self._sms(task)) == []


class TestGetLawyerNames:
    def test_success(self) -> None:
        parser = DocumentParserService(lawyer_service=MagicMock(get_all_lawyer_names=lambda: ["陈律师", "周律师"]))
        assert parser.get_lawyer_names() == ["陈律师", "周律师"]

    def test_failure_returns_empty(self) -> None:
        parser = DocumentParserService(
            lawyer_service=MagicMock(get_all_lawyer_names=MagicMock(side_effect=RuntimeError("x")))
        )
        assert parser.get_lawyer_names() == []
