"""
CallSiteUpdater 单元测试
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .call_site_updater import CallSite, CallSiteUpdater, CallSiteUpdateReport, FileCallSiteReport


@pytest.fixture
def updater() -> CallSiteUpdater:
    return CallSiteUpdater()


# ── scan_call_sites ─────────────────────────────────────────


class TestScanCallSites:
    """测试调用点扫描"""

    def test_finds_simple_call(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """扫描到简单的 ClassName.method() 调用"""
        caller = tmp_path / "caller.py"
        caller.write_text(
            "from services import MyService\n" "\n" "result = MyService.do_work(a, b)\n",
            encoding="utf-8",
        )
        sites = updater.scan_call_sites(
            tmp_path,
            "MyService",
            "do_work",
        )
        assert len(sites) == 1
        assert sites[0].line_number == 3
        assert sites[0].class_name == "MyService"
        assert sites[0].method_name == "do_work"

    def test_skips_comments(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """跳过注释中的调用"""
        caller = tmp_path / "caller.py"
        caller.write_text(
            "# MyService.do_work(a)\n" "x = 1\n",
            encoding="utf-8",
        )
        sites = updater.scan_call_sites(
            tmp_path,
            "MyService",
            "do_work",
        )
        assert len(sites) == 0

    def test_excludes_file(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """排除指定文件"""
        definition = tmp_path / "service.py"
        definition.write_text(
            "class MyService:\n" "    def do_work(self): pass\n" "    MyService.do_work()\n",
            encoding="utf-8",
        )
        caller = tmp_path / "caller.py"
        caller.write_text(
            "MyService.do_work()\n",
            encoding="utf-8",
        )
        sites = updater.scan_call_sites(
            tmp_path,
            "MyService",
            "do_work",
            exclude_file=definition,
        )
        assert len(sites) == 1
        assert sites[0].file_path == str(caller)

    def test_multiple_calls_in_file(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """同一文件中多个调用点"""
        caller = tmp_path / "caller.py"
        caller.write_text(
            "a = MyService.do_work(1)\n" "b = MyService.do_work(2)\n",
            encoding="utf-8",
        )
        sites = updater.scan_call_sites(
            tmp_path,
            "MyService",
            "do_work",
        )
        assert len(sites) == 2

    def test_no_match(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """没有匹配的调用"""
        caller = tmp_path / "caller.py"
        caller.write_text(
            "x = OtherService.do_work()\n",
            encoding="utf-8",
        )
        sites = updater.scan_call_sites(
            tmp_path,
            "MyService",
            "do_work",
        )
        assert len(sites) == 0

    def test_excludes_pycache(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """排除 __pycache__ 目录"""
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        cached = cache_dir / "caller.py"
        cached.write_text("MyService.do_work()\n", encoding="utf-8")

        sites = updater.scan_call_sites(
            tmp_path,
            "MyService",
            "do_work",
        )
        assert len(sites) == 0


# ── update_call_sites ───────────────────────────────────────


class TestUpdateCallSites:
    """测试调用点更新"""

    def test_replace_with_instance_var(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """替换为实例变量调用"""
        caller = tmp_path / "caller.py"
        caller.write_text(
            "from services import MyService\n" "\n" "result = MyService.do_work(a, b)\n",
            encoding="utf-8",
        )
        report = updater.update_call_sites(
            tmp_path,
            "MyService",
            "do_work",
        )
        assert report.total_call_sites_updated == 1

        content = caller.read_text(encoding="utf-8")
        assert "my_service.do_work(a, b)" in content
        assert "MyService.do_work" not in content

    def test_dry_run_no_write(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """dry_run 模式不写入文件"""
        caller = tmp_path / "caller.py"
        original = "from services import MyService\n" "\n" "result = MyService.do_work(a)\n"
        caller.write_text(original, encoding="utf-8")

        report = updater.update_call_sites(
            tmp_path,
            "MyService",
            "do_work",
            dry_run=True,
        )
        assert report.total_call_sites_found == 1
        # 文件内容不变
        assert caller.read_text(encoding="utf-8") == original

    def test_same_class_uses_self(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """同类内部调用替换为 self.method()"""
        caller = tmp_path / "caller.py"
        caller.write_text(
            "class MyService:\n" "    def other(self):\n" "        return MyService.do_work(1)\n",
            encoding="utf-8",
        )
        report = updater.update_call_sites(
            tmp_path,
            "MyService",
            "do_work",
        )
        assert report.total_call_sites_updated == 1

        content = caller.read_text(encoding="utf-8")
        assert "self.do_work(1)" in content

    def test_existing_instance_reused(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """已有实例变量时复用"""
        caller = tmp_path / "caller.py"
        caller.write_text(
            "from services import MyService\n" "\n" "svc = MyService()\n" "result = MyService.do_work(a)\n",
            encoding="utf-8",
        )
        report = updater.update_call_sites(
            tmp_path,
            "MyService",
            "do_work",
        )
        content = caller.read_text(encoding="utf-8")
        assert "my_service.do_work(a)" in content
        # 不应重复插入实例化代码
        assert content.count("MyService()") == 1

    def test_inserts_instantiation_when_needed(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """没有实例时插入实例化代码"""
        caller = tmp_path / "caller.py"
        caller.write_text(
            "from services import MyService\n" "\n" "def handler():\n" "    return MyService.do_work(a)\n",
            encoding="utf-8",
        )
        report = updater.update_call_sites(
            tmp_path,
            "MyService",
            "do_work",
        )
        content = caller.read_text(encoding="utf-8")
        assert "my_service = MyService()" in content
        assert "my_service.do_work(a)" in content

    def test_multiple_files(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """跨多个文件更新"""
        f1 = tmp_path / "a.py"
        f1.write_text("x = Svc.run()\n", encoding="utf-8")
        f2 = tmp_path / "b.py"
        f2.write_text("y = Svc.run()\n", encoding="utf-8")

        report = updater.update_call_sites(
            tmp_path,
            "Svc",
            "run",
        )
        assert report.total_call_sites_updated == 2
        assert report.total_files_scanned == 2

    def test_syntax_error_reported(
        self,
        updater: CallSiteUpdater,
        tmp_path: Path,
    ) -> None:
        """语法错误的文件不会被扫描到调用点"""
        bad = tmp_path / "bad.py"
        bad.write_text("def (\n", encoding="utf-8")

        report = updater.update_call_sites(
            tmp_path,
            "MyService",
            "do_work",
        )
        assert report.total_call_sites_found == 0


# ── 辅助方法 ────────────────────────────────────────────────


class TestHelperMethods:
    """测试辅助方法"""

    def test_to_snake_case(self) -> None:
        assert CallSiteUpdater._to_snake_case("MyService") == "my_service"
        assert CallSiteUpdater._to_snake_case("HTTPClient") == "h_t_t_p_client"
        assert CallSiteUpdater._to_snake_case("Svc") == "svc"

    def test_find_import_end(self) -> None:
        lines = [
            "import os\n",
            "from pathlib import Path\n",
            "\n",
            "x = 1\n",
        ]
        idx = CallSiteUpdater._find_import_end(lines)
        assert idx == 2  # 第二个 import 之后

    def test_find_import_end_no_imports(self) -> None:
        lines = [
            "x = 1\n",
            "y = 2\n",
        ]
        idx = CallSiteUpdater._find_import_end(lines)
        assert idx == 0

    def test_find_existing_instance_true(
        self,
        updater: CallSiteUpdater,
    ) -> None:
        source = "svc = MyService()\nresult = svc.run()\n"
        assert (
            updater._find_existing_instance(
                source,
                "MyService",
                "my_service",
            )
            is True
        )

    def test_find_existing_instance_false(
        self,
        updater: CallSiteUpdater,
    ) -> None:
        source = "result = MyService.run()\n"
        assert (
            updater._find_existing_instance(
                source,
                "MyService",
                "my_service",
            )
            is False
        )

    def test_is_in_class(self) -> None:
        assert CallSiteUpdater._is_in_class(5, [(1, 10)]) is True
        assert CallSiteUpdater._is_in_class(15, [(1, 10)]) is False
        assert CallSiteUpdater._is_in_class(5, []) is False
