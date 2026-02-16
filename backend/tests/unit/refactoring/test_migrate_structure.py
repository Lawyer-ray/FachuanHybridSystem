"""
迁移工具单元测试

测试 MoveFileMigration, CreateDirectoryMigration, DeleteFileMigration 和 StructureMigrator
"""

import shutil
import tempfile

import pytest

from apps.core.path import Path
from scripts.refactoring.migrate_structure import (
    CreateDirectoryMigration,
    DeleteFileMigration,
    MoveFileMigration,
    StructureMigrator,
)


class TestMoveFileMigration:
    """测试 MoveFileMigration 的文件移动功能"""

    def setup_method(self):
        """每个测试方法前执行"""
        # 创建临时目录
        self.temp_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        """每个测试方法后执行"""
        # 清理临时目录
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_move_file_success(self):
        """测试文件移动成功"""
        # 准备测试数据
        source = self.temp_dir / "source.txt"
        destination = self.temp_dir / "dest" / "destination.txt"
        source.write_text("test content")

        # 执行迁移
        migration = MoveFileMigration(source, destination)
        migration.execute(dry_run=False)

        # 验证结果
        assert destination.exists()
        assert destination.read_text() == "test content"
        assert not source.exists()

    def test_move_file_dry_run(self):
        """测试 dry-run 模式不实际移动文件"""
        # 准备测试数据
        source = self.temp_dir / "source.txt"
        destination = self.temp_dir / "destination.txt"
        source.write_text("test content")

        # 执行 dry-run
        migration = MoveFileMigration(source, destination)
        migration.execute(dry_run=True)

        # 验证文件未移动
        assert source.exists()
        assert not destination.exists()

    def test_move_file_source_not_exists(self):
        """测试源文件不存在时抛出异常"""
        source = self.temp_dir / "nonexistent.txt"
        destination = self.temp_dir / "destination.txt"

        migration = MoveFileMigration(source, destination)

        with pytest.raises(FileNotFoundError):
            migration.execute(dry_run=False)

    def test_move_file_destination_exists(self):
        """测试目标文件已存在时备份"""
        # 准备测试数据
        source = self.temp_dir / "source.txt"
        destination = self.temp_dir / "destination.txt"
        source.write_text("new content")
        destination.write_text("old content")

        # 执行迁移
        migration = MoveFileMigration(source, destination)
        migration.execute(dry_run=False)

        # 验证结果
        assert destination.exists()
        assert destination.read_text() == "new content"
        assert not source.exists()

        # 验证备份文件存在
        backup_path = destination.with_suffix(destination.suffix + ".backup")
        assert backup_path.exists()
        assert backup_path.read_text() == "old content"

    def test_move_file_rollback(self):
        """测试文件移动回滚"""
        # 准备测试数据
        source = self.temp_dir / "source.txt"
        destination = self.temp_dir / "destination.txt"
        source.write_text("test content")

        # 执行迁移
        migration = MoveFileMigration(source, destination)
        migration.execute(dry_run=False)

        # 验证移动成功
        assert destination.exists()
        assert not source.exists()

        # 执行回滚
        migration.rollback()

        # 验证回滚成功
        assert source.exists()
        assert source.read_text() == "test content"
        assert not destination.exists()

    def test_move_file_rollback_with_backup(self):
        """测试有备份文件时的回滚"""
        # 准备测试数据
        source = self.temp_dir / "source.txt"
        destination = self.temp_dir / "destination.txt"
        source.write_text("new content")
        destination.write_text("old content")

        # 执行迁移
        migration = MoveFileMigration(source, destination)
        migration.execute(dry_run=False)

        # 执行回滚
        migration.rollback()

        # 验证回滚成功
        assert source.exists()
        assert source.read_text() == "new content"
        assert destination.exists()
        assert destination.read_text() == "old content"


class TestCreateDirectoryMigration:
    """测试 CreateDirectoryMigration 的目录创建功能"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.temp_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        """每个测试方法后执行"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_create_directory_success(self):
        """测试目录创建成功"""
        # 准备测试数据
        path = self.temp_dir / "new_dir"

        # 执行迁移
        migration = CreateDirectoryMigration(path)
        migration.execute(dry_run=False)

        # 验证结果
        assert path.exists()
        assert path.is_dir()

    def test_create_directory_dry_run(self):
        """测试 dry-run 模式不实际创建目录"""
        # 准备测试数据
        path = self.temp_dir / "new_dir"

        # 执行 dry-run
        migration = CreateDirectoryMigration(path)
        migration.execute(dry_run=True)

        # 验证目录未创建
        assert not path.exists()

    def test_create_directory_already_exists(self):
        """测试目录已存在时不报错"""
        # 准备测试数据
        path = self.temp_dir / "existing_dir"
        path.mkdir()

        # 执行迁移
        migration = CreateDirectoryMigration(path)
        migration.execute(dry_run=False)

        # 验证目录仍然存在
        assert path.exists()
        assert path.is_dir()

    def test_create_nested_directory(self):
        """测试创建嵌套目录"""
        # 准备测试数据
        path = self.temp_dir / "level1" / "level2" / "level3"

        # 执行迁移
        migration = CreateDirectoryMigration(path)
        migration.execute(dry_run=False)

        # 验证结果
        assert path.exists()
        assert path.is_dir()

    def test_create_directory_rollback(self):
        """测试目录创建回滚"""
        # 准备测试数据
        path = self.temp_dir / "new_dir"

        # 执行迁移
        migration = CreateDirectoryMigration(path)
        migration.execute(dry_run=False)

        # 验证创建成功
        assert path.exists()

        # 执行回滚
        migration.rollback()

        # 验证回滚成功
        assert not path.exists()

    def test_create_directory_rollback_not_empty(self):
        """测试非空目录不会被回滚删除"""
        # 准备测试数据
        path = self.temp_dir / "new_dir"

        # 执行迁移
        migration = CreateDirectoryMigration(path)
        migration.execute(dry_run=False)

        # 在目录中创建文件
        (path / "file.txt").write_text("content")

        # 执行回滚
        migration.rollback()

        # 验证目录未被删除
        assert path.exists()

    def test_create_directory_rollback_existing(self):
        """测试已存在的目录不会被回滚删除"""
        # 准备测试数据
        path = self.temp_dir / "existing_dir"
        path.mkdir()

        # 执行迁移
        migration = CreateDirectoryMigration(path)
        migration.execute(dry_run=False)

        # 执行回滚
        migration.rollback()

        # 验证目录未被删除
        assert path.exists()


class TestDeleteFileMigration:
    """测试 DeleteFileMigration 的文件删除和回滚功能"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.temp_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        """每个测试方法后执行"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_delete_file_success(self):
        """测试文件删除成功"""
        # 准备测试数据
        path = self.temp_dir / "file.txt"
        path.write_text("test content")

        # 执行迁移
        migration = DeleteFileMigration(path)
        migration.execute(dry_run=False)

        # 验证文件已删除
        assert not path.exists()

        # 验证备份文件存在
        backup_path = path.with_suffix(path.suffix + ".backup")
        assert backup_path.exists()
        assert backup_path.read_text() == "test content"

    def test_delete_file_dry_run(self):
        """测试 dry-run 模式不实际删除文件"""
        # 准备测试数据
        path = self.temp_dir / "file.txt"
        path.write_text("test content")

        # 执行 dry-run
        migration = DeleteFileMigration(path)
        migration.execute(dry_run=True)

        # 验证文件未删除
        assert path.exists()

    def test_delete_file_not_exists(self):
        """测试删除不存在的文件不报错"""
        # 准备测试数据
        path = self.temp_dir / "nonexistent.txt"

        # 执行迁移（不应该抛出异常）
        migration = DeleteFileMigration(path)
        migration.execute(dry_run=False)

        # 验证没有异常
        assert not path.exists()

    def test_delete_file_rollback(self):
        """测试文件删除回滚"""
        # 准备测试数据
        path = self.temp_dir / "file.txt"
        path.write_text("test content")

        # 执行迁移
        migration = DeleteFileMigration(path)
        migration.execute(dry_run=False)

        # 验证删除成功
        assert not path.exists()

        # 执行回滚
        migration.rollback()

        # 验证回滚成功
        assert path.exists()
        assert path.read_text() == "test content"


class TestStructureMigrator:
    """测试 StructureMigrator 的迁移管理功能"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.migrator = StructureMigrator(self.temp_dir)

    def teardown_method(self):
        """每个测试方法后执行"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_add_migration(self):
        """测试添加迁移任务"""
        migration = CreateDirectoryMigration(self.temp_dir / "test")
        self.migrator.add_migration(migration)

        assert len(self.migrator.migrations) == 1
        assert self.migrator.migrations[0] == migration

    def test_execute_multiple_migrations(self):
        """测试执行多个迁移任务"""
        # 添加多个迁移任务
        dir1 = self.temp_dir / "dir1"
        dir2 = self.temp_dir / "dir2"
        file1 = self.temp_dir / "file1.txt"

        self.migrator.add_migration(CreateDirectoryMigration(dir1))
        self.migrator.add_migration(CreateDirectoryMigration(dir2))

        # 创建源文件
        file1.write_text("content")
        file2 = dir1 / "file2.txt"

        self.migrator.add_migration(MoveFileMigration(file1, file2))

        # 执行迁移
        self.migrator.execute(dry_run=False)

        # 验证结果
        assert dir1.exists()
        assert dir2.exists()
        assert file2.exists()
        assert not file1.exists()

    def test_execute_dry_run(self):
        """测试 dry-run 模式"""
        # 添加迁移任务
        dir1 = self.temp_dir / "dir1"
        self.migrator.add_migration(CreateDirectoryMigration(dir1))

        # 执行 dry-run
        self.migrator.execute(dry_run=True)

        # 验证未实际执行
        assert not dir1.exists()

    def test_execute_with_error_triggers_rollback(self):
        """测试执行失败时触发回滚"""
        # 添加迁移任务
        dir1 = self.temp_dir / "dir1"
        file1 = self.temp_dir / "nonexistent.txt"
        file2 = self.temp_dir / "dest.txt"

        self.migrator.add_migration(CreateDirectoryMigration(dir1))
        self.migrator.add_migration(MoveFileMigration(file1, file2))  # 这个会失败

        # 执行迁移（应该失败）
        with pytest.raises(FileNotFoundError):
            self.migrator.execute(dry_run=False)

        # 验证回滚：第一个迁移应该被回滚
        assert not dir1.exists()

    def test_rollback_all_migrations(self):
        """测试回滚所有迁移"""
        # 添加并执行迁移
        dir1 = self.temp_dir / "dir1"
        dir2 = self.temp_dir / "dir2"

        self.migrator.add_migration(CreateDirectoryMigration(dir1))
        self.migrator.add_migration(CreateDirectoryMigration(dir2))

        self.migrator.execute(dry_run=False)

        # 验证创建成功
        assert dir1.exists()
        assert dir2.exists()

        # 执行回滚
        self.migrator.rollback()

        # 验证回滚成功
        assert not dir1.exists()
        assert not dir2.exists()

    def test_rollback_partial_migrations(self):
        """测试回滚部分迁移"""
        # 添加并执行迁移
        dir1 = self.temp_dir / "dir1"
        dir2 = self.temp_dir / "dir2"
        dir3 = self.temp_dir / "dir3"

        self.migrator.add_migration(CreateDirectoryMigration(dir1))
        self.migrator.add_migration(CreateDirectoryMigration(dir2))
        self.migrator.add_migration(CreateDirectoryMigration(dir3))

        self.migrator.execute(dry_run=False)

        # 验证创建成功
        assert dir1.exists()
        assert dir2.exists()
        assert dir3.exists()

        # 只回滚前两个迁移
        self.migrator.rollback(executed_count=2)

        # 验证回滚结果
        assert not dir1.exists()
        assert not dir2.exists()
        assert dir3.exists()  # 第三个不应该被回滚

    def test_complex_migration_workflow(self):
        """测试复杂的迁移工作流"""
        # 创建复杂的迁移场景
        # 1. 创建目录
        dir1 = self.temp_dir / "source"
        dir2 = self.temp_dir / "dest"

        # 2. 创建源文件
        source_file = self.temp_dir / "file.txt"
        source_file.write_text("original content")

        # 3. 添加迁移任务
        self.migrator.add_migration(CreateDirectoryMigration(dir1))
        self.migrator.add_migration(CreateDirectoryMigration(dir2))
        self.migrator.add_migration(MoveFileMigration(source_file, dir2 / "file.txt"))

        # 4. 执行迁移
        self.migrator.execute(dry_run=False)

        # 5. 验证结果
        assert dir1.exists()
        assert dir2.exists()
        assert (dir2 / "file.txt").exists()
        assert (dir2 / "file.txt").read_text() == "original content"
        assert not source_file.exists()

        # 6. 执行回滚
        self.migrator.rollback()

        # 7. 验证回滚
        assert not dir1.exists()
        assert not dir2.exists()
        assert source_file.exists()
        assert source_file.read_text() == "original content"
