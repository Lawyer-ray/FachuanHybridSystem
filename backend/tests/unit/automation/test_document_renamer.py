"""
DocumentRenamer 服务单元测试
"""
import tempfile
from datetime import date
from apps.core.path import Path
from unittest.mock import patch, MagicMock

import pytest

from apps.automation.services.sms.document_renamer import DocumentRenamer
from apps.core.exceptions import ValidationException


class TestDocumentRenamer:
    """DocumentRenamer 测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.renamer = DocumentRenamer()
    
    def test_generate_filename_basic(self):
        """测试基本文件名生成"""
        title = "裁定书"
        case_name = "张三诉李四合同纠纷案"
        received_date = date(2025, 12, 14)
        
        filename = self.renamer.generate_filename(title, case_name, received_date)
        
        assert filename == "裁定书（张三诉李四合同纠纷案）_20251214收.pdf"
    
    def test_generate_filename_with_illegal_chars(self):
        """测试包含非法字符的文件名生成"""
        title = "裁定书<test>"
        case_name = "张三|李四:合同纠纷"
        received_date = date(2025, 12, 14)
        
        filename = self.renamer.generate_filename(title, case_name, received_date)
        
        # 非法字符应被移除
        assert "<" not in filename
        assert ">" not in filename
        assert "|" not in filename
        assert ":" not in filename
        assert filename == "裁定书test（张三李四合同纠纷）_20251214收.pdf"
    
    def test_generate_filename_with_long_names(self):
        """测试长名称的处理"""
        title = "这是一个非常长的文书标题名称超过了二十个字符的限制"
        case_name = "这是一个非常长的案件名称超过了六十个字符的限制应该被截断处理" * 2
        received_date = date(2025, 12, 14)

        with patch("apps.automation.services.sms.document_renamer.get_config") as mock_get_config:
            def _fake_get_config(key, default=None):
                if key == "features.document_renaming.title_max_length":
                    return 20
                if key == "features.document_renaming.case_name_max_length":
                    return 60
                if key == "features.document_renaming.case_name_hash_length":
                    return 6
                return default

            mock_get_config.side_effect = _fake_get_config
            filename = self.renamer.generate_filename(title, case_name, received_date)
        
        # 检查长度限制
        parts = filename.split('（')
        title_part = parts[0]
        assert len(title_part) <= 20
        
        case_part = parts[1].split('）')[0]
        assert len(case_part) <= 60
        assert len(case_part) > 30
    
    def test_generate_filename_with_empty_values(self):
        """测试空值处理"""
        filename = self.renamer.generate_filename("", "", date(2025, 12, 14))
        
        assert filename == "司法文书（未知案件）_20251214收.pdf"
    
    def test_sanitize_filename_part(self):
        """测试文件名清理"""
        # 测试非法字符移除
        result = self.renamer._sanitize_filename_part("test<>:\"|?*\\/file")
        assert result == "testfile"
        
        # 测试首尾空格和点号移除
        result = self.renamer._sanitize_filename_part("  .test.  ")
        assert result == "test"
    
    def test_clean_extracted_title(self):
        """测试标题清理"""
        # 测试移除案号
        result = self.renamer._clean_extracted_title("裁定书（2025）粤0604执保9654号")
        assert result == "裁定书"
        
        # 测试移除引号
        result = self.renamer._clean_extracted_title('"判决书"')
        assert result == "判决书"
        
        # 测试标准文书类型识别
        result = self.renamer._clean_extracted_title("这是一个执行通知书的标题")
        assert result == "执行通知书"
    
    def test_extract_title_from_filename(self):
        """测试从文件名提取标题"""
        # 测试标准文书类型
        result = self.renamer._extract_title_from_filename("/path/to/执行裁定书.pdf")
        assert result == "执行裁定书"
        
        # 测试无匹配情况
        result = self.renamer._extract_title_from_filename("/path/to/unknown_file.pdf")
        assert result == "司法文书"
    
    def test_extract_document_title_file_not_exists(self):
        """测试文件不存在的情况"""
        with pytest.raises(ValidationException, match="文书文件不存在"):
            self.renamer.extract_document_title("/nonexistent/file.pdf")
    
    @patch('apps.automation.services.sms.document_renamer.extract_document_content')
    def test_extract_document_title_no_text(self, mock_extract):
        """测试无法提取文本的情况"""
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Mock 返回无文本内容
            mock_extraction = MagicMock()
            mock_extraction.text = None
            mock_extract.return_value = mock_extraction
            
            result = self.renamer.extract_document_title(tmp_path)
            
            # 应该降级到从文件名提取
            assert result == "司法文书"
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    
    @patch('apps.automation.services.sms.document_renamer.extract_document_content')
    @patch('apps.automation.services.sms.document_renamer.chat')
    def test_extract_document_title_with_ollama_success(self, mock_chat, mock_extract):
        """测试 Ollama 成功提取标题"""
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Mock 文档内容提取
            mock_extraction = MagicMock()
            mock_extraction.text = "这是一份执行通知书的内容..."
            mock_extract.return_value = mock_extraction
            
            # Mock Ollama 响应
            mock_chat.return_value = {
                "message": {
                    "content": "执行通知书"
                }
            }
            
            result = self.renamer.extract_document_title(tmp_path)
            
            assert result == "执行通知书"
            mock_chat.assert_called_once()
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    
    def test_rename_file_not_exists(self):
        """测试重命名不存在的文件"""
        with pytest.raises(ValidationException, match="文书文件不存在"):
            self.renamer.rename("/nonexistent/file.pdf", "测试案件", date(2025, 12, 14))
    
    @patch.object(DocumentRenamer, 'extract_document_title')
    def test_rename_success(self, mock_extract_title):
        """测试成功重命名"""
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            mock_extract_title.return_value = "裁定书"
            
            result = self.renamer.rename(tmp_path, "测试案件", date(2025, 12, 14))
            
            # 检查新文件是否存在
            assert Path(result).exists()
            assert "裁定书（测试案件）_20251214收.pdf" in result
            
            # 原文件应该不存在了
            assert not Path(tmp_path).exists()
        finally:
            # 清理
            if Path(tmp_path).exists():
                Path(tmp_path).unlink()
            if 'result' in locals() and Path(result).exists():
                Path(result).unlink()
    
    @patch.object(DocumentRenamer, 'extract_document_title')
    def test_rename_with_conflict(self, mock_extract_title):
        """测试文件名冲突处理"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            
            # 创建原始文件
            original_file = tmp_dir_path / "original.pdf"
            original_file.write_text("test content")
            
            # 创建冲突文件
            conflict_file = tmp_dir_path / "裁定书（测试案件）_20251214收.pdf"
            conflict_file.write_text("conflict content")
            
            mock_extract_title.return_value = "裁定书"
            
            result = self.renamer.rename(str(original_file), "测试案件", date(2025, 12, 14))
            
            # 应该生成带序号的文件名
            assert "裁定书（测试案件）_20251214收(1).pdf" in result
            assert Path(result).exists()
    
    @patch.object(DocumentRenamer, 'rename')
    def test_rename_with_fallback_success(self, mock_rename):
        """测试降级方案成功"""
        mock_rename.side_effect = Exception("重命名失败")
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            result = self.renamer.rename_with_fallback(
                tmp_path, 
                "测试案件", 
                date(2025, 12, 14),
                "原始文书名称"
            )
            
            # 降级方案应该使用原始名称
            assert "原始文书名称（测试案件）_20251214收.pdf" in result
        finally:
            # 清理文件
            for path_str in [tmp_path, result]:
                path = Path(path_str)
                if path.exists():
                    path.unlink()
