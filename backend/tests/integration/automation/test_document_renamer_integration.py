"""
DocumentRenamer 集成测试
"""
import tempfile
from datetime import date
from apps.core.path import Path
from unittest.mock import patch, MagicMock

import pytest

from apps.automation.services.sms.document_renamer import DocumentRenamer


class TestDocumentRenamerIntegration:
    """DocumentRenamer 集成测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.renamer = DocumentRenamer()
    
    @patch('apps.automation.services.sms.document_renamer.extract_document_content')
    @patch('apps.automation.services.sms.document_renamer.chat')
    def test_full_workflow_with_mocked_dependencies(self, mock_chat, mock_extract):
        """测试完整工作流程（Mock 所有外部依赖）"""
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(b'test content')
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
            
            # 执行重命名
            result = self.renamer.rename(
                tmp_path, 
                "张三诉李四合同纠纷案", 
                date(2025, 12, 14)
            )
            
            # 验证结果
            assert Path(result).exists()
            assert "执行通知书（张三诉李四合同纠纷案）_20251214收.pdf" in result
            
            # 原文件应该不存在了
            assert not Path(tmp_path).exists()
            
            # 验证调用
            mock_extract.assert_called_once_with(tmp_path, limit=500)
            mock_chat.assert_called_once()
            
        finally:
            # 清理文件
            for path_str in [tmp_path, result if 'result' in locals() else None]:
                if path_str:
                    path = Path(path_str)
                    if path.exists():
                        path.unlink()
    
    def test_fallback_workflow(self):
        """测试降级工作流程"""
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(b'test content')
            tmp_path = tmp.name
        
        try:
            # 直接测试 rename_with_fallback，它会处理所有异常
            result = self.renamer.rename_with_fallback(
                tmp_path, 
                "测试案件", 
                date(2025, 12, 14),
                "原始文书名称"
            )
            
            # 验证结果 - 应该使用原始文书名称作为降级
            assert Path(result).exists()
            assert "原始文书名称（测试案件）_20251214收.pdf" in result
            
        finally:
            # 清理文件
            for path_str in [tmp_path, result if 'result' in locals() else None]:
                if path_str:
                    path = Path(path_str)
                    if path.exists():
                        path.unlink()
    
    def test_filename_generation_edge_cases(self):
        """测试文件名生成的边界情况"""
        # 测试特殊字符
        filename = self.renamer.generate_filename(
            "执行通知书", 
            "张三/李四|王五:赵六", 
            date(2025, 12, 14)
        )
        
        # 验证非法字符被移除
        assert "/" not in filename
        assert "|" not in filename
        assert ":" not in filename
        assert filename == "执行通知书（张三李四王五赵六）_20251214收.pdf"
        
        # 测试超长名称
        long_title = "这是一个非常长的文书标题" * 5
        long_case = "这是一个非常长的案件名称" * 10
        
        filename = self.renamer.generate_filename(
            long_title, 
            long_case, 
            date(2025, 12, 14)
        )
        
        # 验证长度限制
        parts = filename.split('（')
        title_part = parts[0]
        case_part = parts[1].split('）')[0]
        
        assert len(title_part) <= 20
        assert len(case_part) <= 30
