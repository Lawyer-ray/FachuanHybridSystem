"""
ImageRotationService export_images 单元测试

测试 export_images 方法的 rename_map 参数和文件名冲突处理。

**Validates: Requirements 5.1, 5.2, 5.3**
"""

import base64
import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from apps.automation.services.image_rotation import ImageRotationService


def create_test_image_base64(width: int = 100, height: int = 100, color: str = "red") -> str:
    """创建测试用的 Base64 编码图片"""
    img = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


class TestExportImagesWithRenameMap:
    """测试 export_images 方法的 rename_map 参数
    
    **Validates: Requirements 5.1, 5.2, 5.3**
    """

    @patch.object(ImageRotationService, "_get_output_dir")
    def test_export_without_rename_map_uses_original_filenames(self, mock_output_dir, tmp_path):
        """不提供 rename_map 时使用原始文件名
        
        **Validates: Requirements 5.3**
        """
        mock_output_dir.return_value = tmp_path
        
        service = ImageRotationService()
        images = [
            {
                "filename": "original1.jpg",
                "data": create_test_image_base64(),
                "format": "jpeg",
            },
            {
                "filename": "original2.jpg",
                "data": create_test_image_base64(color="blue"),
                "format": "jpeg",
            },
        ]
        
        result = service.export_images(images)
        
        assert result["success"] is True
        assert "zip_url" in result
        
        # 验证 ZIP 文件内容
        zip_path = tmp_path / result["zip_url"].split("/")[-1]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "original1.jpg" in names
            assert "original2.jpg" in names

    @patch.object(ImageRotationService, "_get_output_dir")
    def test_export_with_rename_map_uses_new_filenames(self, mock_output_dir, tmp_path):
        """提供 rename_map 时使用新文件名
        
        **Validates: Requirements 5.1**
        """
        mock_output_dir.return_value = tmp_path
        
        service = ImageRotationService()
        images = [
            {
                "filename": "IMG_001.jpg",
                "data": create_test_image_base64(),
                "format": "jpeg",
            },
            {
                "filename": "IMG_002.jpg",
                "data": create_test_image_base64(color="blue"),
                "format": "jpeg",
            },
        ]
        
        rename_map = {
            "IMG_001.jpg": "20250630_65500元.jpg",
            "IMG_002.jpg": "20250701_12000元.jpg",
        }
        
        result = service.export_images(images, rename_map=rename_map)
        
        assert result["success"] is True
        
        # 验证 ZIP 文件内容使用了新文件名
        zip_path = tmp_path / result["zip_url"].split("/")[-1]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "20250630_65500元.jpg" in names
            assert "20250701_12000元.jpg" in names
            assert "IMG_001.jpg" not in names
            assert "IMG_002.jpg" not in names

    @patch.object(ImageRotationService, "_get_output_dir")
    def test_export_with_partial_rename_map(self, mock_output_dir, tmp_path):
        """部分文件有映射时，未映射的使用原始文件名
        
        **Validates: Requirements 5.3**
        """
        mock_output_dir.return_value = tmp_path
        
        service = ImageRotationService()
        images = [
            {
                "filename": "IMG_001.jpg",
                "data": create_test_image_base64(),
                "format": "jpeg",
            },
            {
                "filename": "IMG_002.jpg",
                "data": create_test_image_base64(color="blue"),
                "format": "jpeg",
            },
            {
                "filename": "IMG_003.jpg",
                "data": create_test_image_base64(color="green"),
                "format": "jpeg",
            },
        ]
        
        # 只映射部分文件
        rename_map = {
            "IMG_001.jpg": "20250630_65500元.jpg",
            # IMG_002.jpg 没有映射
            "IMG_003.jpg": "20250702_8000元.jpg",
        }
        
        result = service.export_images(images, rename_map=rename_map)
        
        assert result["success"] is True
        
        zip_path = tmp_path / result["zip_url"].split("/")[-1]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "20250630_65500元.jpg" in names
            assert "IMG_002.jpg" in names  # 未映射，保持原名
            assert "20250702_8000元.jpg" in names

    @patch.object(ImageRotationService, "_get_output_dir")
    def test_export_with_empty_rename_map(self, mock_output_dir, tmp_path):
        """空 rename_map 时使用原始文件名"""
        mock_output_dir.return_value = tmp_path
        
        service = ImageRotationService()
        images = [
            {
                "filename": "original.jpg",
                "data": create_test_image_base64(),
                "format": "jpeg",
            },
        ]
        
        result = service.export_images(images, rename_map={})
        
        assert result["success"] is True
        
        zip_path = tmp_path / result["zip_url"].split("/")[-1]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "original.jpg" in names

    @patch.object(ImageRotationService, "_get_output_dir")
    def test_export_with_none_rename_map(self, mock_output_dir, tmp_path):
        """rename_map 为 None 时使用原始文件名"""
        mock_output_dir.return_value = tmp_path
        
        service = ImageRotationService()
        images = [
            {
                "filename": "original.jpg",
                "data": create_test_image_base64(),
                "format": "jpeg",
            },
        ]
        
        result = service.export_images(images, rename_map=None)
        
        assert result["success"] is True
        
        zip_path = tmp_path / result["zip_url"].split("/")[-1]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "original.jpg" in names


class TestFilenameConflictHandling:
    """测试文件名冲突处理
    
    **Validates: Requirements 5.2**
    """

    @patch.object(ImageRotationService, "_get_output_dir")
    def test_duplicate_renamed_filenames_get_sequence_suffix(self, mock_output_dir, tmp_path):
        """重复的新文件名应添加序号后缀
        
        **Validates: Requirements 5.2**
        """
        mock_output_dir.return_value = tmp_path
        
        service = ImageRotationService()
        images = [
            {
                "filename": "IMG_001.jpg",
                "data": create_test_image_base64(),
                "format": "jpeg",
            },
            {
                "filename": "IMG_002.jpg",
                "data": create_test_image_base64(color="blue"),
                "format": "jpeg",
            },
            {
                "filename": "IMG_003.jpg",
                "data": create_test_image_base64(color="green"),
                "format": "jpeg",
            },
        ]
        
        # 所有文件映射到相同的新文件名
        rename_map = {
            "IMG_001.jpg": "20250630_65500元.jpg",
            "IMG_002.jpg": "20250630_65500元.jpg",
            "IMG_003.jpg": "20250630_65500元.jpg",
        }
        
        result = service.export_images(images, rename_map=rename_map)
        
        assert result["success"] is True
        
        zip_path = tmp_path / result["zip_url"].split("/")[-1]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            # 应该有 3 个文件，且文件名唯一
            assert len(names) == 3
            assert len(set(names)) == 3  # 所有文件名唯一
            
            # 第一个保持原名，后续添加序号
            assert "20250630_65500元.jpg" in names
            assert "20250630_65500元_1.jpg" in names
            assert "20250630_65500元_2.jpg" in names

    @patch.object(ImageRotationService, "_get_output_dir")
    def test_mixed_duplicate_and_unique_filenames(self, mock_output_dir, tmp_path):
        """混合重复和唯一文件名的处理
        
        **Validates: Requirements 5.2**
        """
        mock_output_dir.return_value = tmp_path
        
        service = ImageRotationService()
        images = [
            {
                "filename": "IMG_001.jpg",
                "data": create_test_image_base64(),
                "format": "jpeg",
            },
            {
                "filename": "IMG_002.jpg",
                "data": create_test_image_base64(color="blue"),
                "format": "jpeg",
            },
            {
                "filename": "IMG_003.jpg",
                "data": create_test_image_base64(color="green"),
                "format": "jpeg",
            },
            {
                "filename": "IMG_004.jpg",
                "data": create_test_image_base64(color="yellow"),
                "format": "jpeg",
            },
        ]
        
        rename_map = {
            "IMG_001.jpg": "20250630_65500元.jpg",
            "IMG_002.jpg": "20250630_65500元.jpg",  # 重复
            "IMG_003.jpg": "20250701_12000元.jpg",  # 唯一
            "IMG_004.jpg": "20250630_65500元.jpg",  # 重复
        }
        
        result = service.export_images(images, rename_map=rename_map)
        
        assert result["success"] is True
        
        zip_path = tmp_path / result["zip_url"].split("/")[-1]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert len(names) == 4
            assert len(set(names)) == 4  # 所有文件名唯一
            
            assert "20250630_65500元.jpg" in names
            assert "20250630_65500元_1.jpg" in names
            assert "20250630_65500元_2.jpg" in names
            assert "20250701_12000元.jpg" in names


class TestGetUniqueFilename:
    """测试 _get_unique_filename 方法"""

    def test_first_occurrence_keeps_original_name(self):
        """第一次出现的文件名保持不变"""
        service = ImageRotationService()
        used_names = {}
        
        result = service._get_unique_filename("test.jpg", used_names)
        
        assert result == "test.jpg"
        assert used_names["test.jpg"] == 1

    def test_second_occurrence_gets_suffix_1(self):
        """第二次出现的文件名添加 _1 后缀"""
        service = ImageRotationService()
        used_names = {"test.jpg": 1}
        
        result = service._get_unique_filename("test.jpg", used_names)
        
        assert result == "test_1.jpg"
        assert used_names["test.jpg"] == 2

    def test_third_occurrence_gets_suffix_2(self):
        """第三次出现的文件名添加 _2 后缀"""
        service = ImageRotationService()
        used_names = {"test.jpg": 2}
        
        result = service._get_unique_filename("test.jpg", used_names)
        
        assert result == "test_2.jpg"
        assert used_names["test.jpg"] == 3

    def test_handles_filename_without_extension(self):
        """处理无扩展名的文件"""
        service = ImageRotationService()
        used_names = {"noext": 1}
        
        result = service._get_unique_filename("noext", used_names)
        
        assert result == "noext_1"

    def test_handles_empty_filename(self):
        """处理空文件名"""
        service = ImageRotationService()
        used_names = {}
        
        result = service._get_unique_filename("", used_names)
        
        # 空文件名应该生成一个默认名称
        assert result.startswith("image_")
        assert result.endswith(".jpg")

    def test_handles_chinese_filename(self):
        """处理中文文件名"""
        service = ImageRotationService()
        used_names = {"20250630_65500元.jpg": 1}
        
        result = service._get_unique_filename("20250630_65500元.jpg", used_names)
        
        assert result == "20250630_65500元_1.jpg"

    def test_preserves_extension_case(self):
        """保留扩展名大小写"""
        service = ImageRotationService()
        used_names = {"test.JPG": 1}
        
        result = service._get_unique_filename("test.JPG", used_names)
        
        assert result == "test_1.JPG"


class TestExportImagesEdgeCases:
    """测试 export_images 边界情况"""

    def test_empty_images_list_returns_error(self):
        """空图片列表返回错误"""
        service = ImageRotationService()
        
        result = service.export_images([])
        
        assert result["success"] is False
        assert "没有图片" in result["message"]

    def test_empty_images_list_with_rename_map_returns_error(self):
        """空图片列表带 rename_map 返回错误"""
        service = ImageRotationService()
        
        result = service.export_images([], rename_map={"a.jpg": "b.jpg"})
        
        assert result["success"] is False
        assert "没有图片" in result["message"]

    @patch.object(ImageRotationService, "_get_output_dir")
    def test_rename_map_with_empty_string_value_keeps_original(self, mock_output_dir, tmp_path):
        """rename_map 值为空字符串时保持原文件名"""
        mock_output_dir.return_value = tmp_path
        
        service = ImageRotationService()
        images = [
            {
                "filename": "original.jpg",
                "data": create_test_image_base64(),
                "format": "jpeg",
            },
        ]
        
        # 空字符串值应该被忽略，保持原文件名
        rename_map = {"original.jpg": ""}
        
        result = service.export_images(images, rename_map=rename_map)
        
        assert result["success"] is True
        
        zip_path = tmp_path / result["zip_url"].split("/")[-1]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            # 空字符串被忽略，保持原文件名
            assert "original.jpg" in names

    @patch.object(ImageRotationService, "_get_output_dir")
    def test_export_with_paper_size_and_rename_map(self, mock_output_dir, tmp_path):
        """同时使用 paper_size 和 rename_map"""
        mock_output_dir.return_value = tmp_path
        
        service = ImageRotationService()
        images = [
            {
                "filename": "IMG_001.jpg",
                "data": create_test_image_base64(),
                "format": "jpeg",
            },
        ]
        
        rename_map = {"IMG_001.jpg": "20250630_65500元.jpg"}
        
        result = service.export_images(images, paper_size="a4", rename_map=rename_map)
        
        assert result["success"] is True
        
        zip_path = tmp_path / result["zip_url"].split("/")[-1]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "20250630_65500元.jpg" in names
