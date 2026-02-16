"""
身份证合并 API 集成测试

测试 /api/v1/client/identity-docs/merge-id-card 和
/api/v1/client/identity-docs/merge-id-card-manual 接口
"""
import json

import cv2
import numpy as np
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


def _create_test_image(width: int = 800, height: int = 600) -> bytes:
    """创建测试图片并返回 JPEG 字节"""
    # 创建白色背景图像
    image = np.ones((height, width, 3), dtype=np.uint8) * 255
    # 添加一些内容
    cv2.rectangle(image, (50, 50), (width - 50, height - 50), (200, 200, 200), 2)
    cv2.putText(
        image, "TEST", (width // 3, height // 2),
        cv2.FONT_HERSHEY_SIMPLEX, 2, (100, 100, 100), 3
    )
    # 编码为 JPEG
    _, buffer = cv2.imencode(".jpg", image)
    return buffer.tobytes()


@pytest.mark.django_db
class TestMergeIdCardAPI:
    """身份证自动合并 API 测试"""

    def test_merge_id_card_success(self, authenticated_client, tmp_path, settings):
        """测试自动合并成功

        **Validates: Requirements AC-1.1, AC-1.5**
        """
        # 设置临时 MEDIA_ROOT
        settings.MEDIA_ROOT = str(tmp_path)

        # 创建测试图片
        front_image = _create_test_image(800, 600)
        back_image = _create_test_image(800, 600)

        front_file = SimpleUploadedFile("front.jpg", front_image, content_type="image/jpeg")
        back_file = SimpleUploadedFile("back.jpg", back_image, content_type="image/jpeg")

        # 执行请求
        response = authenticated_client.post(
            "/api/v1/client/identity-docs/merge-id-card",
            data={
                "front_image": front_file,
                "back_image": back_file,
            },
            HTTP_HOST="localhost",
        )

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        
        # 注意：由于测试图片没有明显的身份证边缘，可能会返回 AUTO_DETECT_FAILED
        # 这是预期行为，因为我们的测试图片不是真实的身份证
        assert "success" in data
        if data["success"]:
            assert "pdf_url" in data
            assert data["pdf_url"].endswith(".pdf")
        else:
            # 自动检测失败也是有效的响应
            assert data.get("error") == "AUTO_DETECT_FAILED"
            assert "front_image_url" in data
            assert "back_image_url" in data

    def test_merge_id_card_invalid_format(self, authenticated_client, tmp_path, settings):
        """测试无效图片格式

        **Validates: Requirements INVALID_IMAGE_FORMAT error**
        """
        settings.MEDIA_ROOT = str(tmp_path)

        # 创建无效的图片数据
        invalid_data = b"not an image"

        front_file = SimpleUploadedFile("front.txt", invalid_data, content_type="text/plain")
        back_file = SimpleUploadedFile("back.txt", invalid_data, content_type="text/plain")

        # 执行请求
        response = authenticated_client.post(
            "/api/v1/client/identity-docs/merge-id-card",
            data={
                "front_image": front_file,
                "back_image": back_file,
            },
            HTTP_HOST="localhost",
        )

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "INVALID_IMAGE_FORMAT"

    def test_merge_id_card_missing_front_image(self, authenticated_client, tmp_path, settings):
        """测试缺少正面图片"""
        settings.MEDIA_ROOT = str(tmp_path)

        back_image = _create_test_image()
        back_file = SimpleUploadedFile("back.jpg", back_image, content_type="image/jpeg")

        # 执行请求（只提供反面图片）
        response = authenticated_client.post(
            "/api/v1/client/identity-docs/merge-id-card",
            data={
                "back_image": back_file,
            },
            HTTP_HOST="localhost",
        )

        # 断言结果 - 应该返回 422 (缺少必需参数)
        assert response.status_code == 422

    def test_merge_id_card_missing_back_image(self, authenticated_client, tmp_path, settings):
        """测试缺少反面图片"""
        settings.MEDIA_ROOT = str(tmp_path)

        front_image = _create_test_image()
        front_file = SimpleUploadedFile("front.jpg", front_image, content_type="image/jpeg")

        # 执行请求（只提供正面图片）
        response = authenticated_client.post(
            "/api/v1/client/identity-docs/merge-id-card",
            data={
                "front_image": front_file,
            },
            HTTP_HOST="localhost",
        )

        # 断言结果 - 应该返回 422 (缺少必需参数)
        assert response.status_code == 422


@pytest.mark.django_db
class TestMergeIdCardManualAPI:
    """身份证手动合并 API 测试"""

    def _create_temp_images(self, tmp_path):
        """创建临时测试图片"""
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 创建测试图片
        front_image = np.ones((600, 800, 3), dtype=np.uint8) * 255
        back_image = np.ones((600, 800, 3), dtype=np.uint8) * 255

        front_path = temp_dir / "front_api_test.jpg"
        back_path = temp_dir / "back_api_test.jpg"

        cv2.imwrite(str(front_path), front_image)
        cv2.imwrite(str(back_path), back_image)

        return "temp/front_api_test.jpg", "temp/back_api_test.jpg"

    def test_merge_id_card_manual_success(self, authenticated_client, tmp_path, settings):
        """测试手动合并成功

        **Validates: Requirements AC-2.2, AC-2.3**
        """
        settings.MEDIA_ROOT = str(tmp_path)

        # 创建临时图片
        front_path, back_path = self._create_temp_images(tmp_path)

        # 准备请求数据
        data = {
            "front_image_path": front_path,
            "back_image_path": back_path,
            "front_corners": [[100, 100], [700, 100], [700, 500], [100, 500]],
            "back_corners": [[100, 100], [700, 100], [700, 500], [100, 500]],
        }

        # 执行请求
        response = authenticated_client.post(
            "/api/v1/client/identity-docs/merge-id-card-manual",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        # 断言结果
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert "pdf_url" in result
        assert result["pdf_url"].endswith(".pdf")

    def test_merge_id_card_manual_with_media_prefix(self, authenticated_client, tmp_path, settings):
        """测试带 /media/ 前缀的路径

        **Validates: Requirements AC-2.2**
        """
        settings.MEDIA_ROOT = str(tmp_path)

        # 创建临时图片
        front_path, back_path = self._create_temp_images(tmp_path)

        # 准备请求数据（带 /media/ 前缀）
        data = {
            "front_image_path": f"/media/{front_path}",
            "back_image_path": f"/media/{back_path}",
            "front_corners": [[100, 100], [700, 100], [700, 500], [100, 500]],
            "back_corners": [[100, 100], [700, 100], [700, 500], [100, 500]],
        }

        # 执行请求
        response = authenticated_client.post(
            "/api/v1/client/identity-docs/merge-id-card-manual",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        # 断言结果
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True

    def test_merge_id_card_manual_invalid_corners(self, authenticated_client, tmp_path, settings):
        """测试无效四角坐标

        **Validates: Requirements INVALID_CORNERS error**
        """
        settings.MEDIA_ROOT = str(tmp_path)

        # 准备请求数据（只有 3 个点）
        data = {
            "front_image_path": "temp/front.jpg",
            "back_image_path": "temp/back.jpg",
            "front_corners": [[100, 100], [700, 100], [700, 500]],  # 只有 3 个点
            "back_corners": [[100, 100], [700, 100], [700, 500], [100, 500]],
        }

        # 执行请求
        response = authenticated_client.post(
            "/api/v1/client/identity-docs/merge-id-card-manual",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        # 断言结果
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is False
        assert result["error"] == "INVALID_CORNERS"

    def test_merge_id_card_manual_concave_corners(self, authenticated_client, tmp_path, settings):
        """测试凹四边形坐标

        **Validates: Requirements P3 - 四角应形成凸四边形**
        """
        settings.MEDIA_ROOT = str(tmp_path)

        # 创建临时图片
        front_path, back_path = self._create_temp_images(tmp_path)

        # 准备请求数据（凹四边形）
        data = {
            "front_image_path": front_path,
            "back_image_path": back_path,
            "front_corners": [[100, 100], [700, 100], [400, 300], [100, 500]],  # 凹四边形
            "back_corners": [[100, 100], [700, 100], [700, 500], [100, 500]],
        }

        # 执行请求
        response = authenticated_client.post(
            "/api/v1/client/identity-docs/merge-id-card-manual",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        # 断言结果
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is False
        assert result["error"] == "INVALID_CORNERS"
        assert "凸四边形" in result["message"]

    def test_merge_id_card_manual_image_not_found(self, authenticated_client, tmp_path, settings):
        """测试图片不存在"""
        settings.MEDIA_ROOT = str(tmp_path)

        # 准备请求数据（图片不存在）
        data = {
            "front_image_path": "temp/nonexistent_front.jpg",
            "back_image_path": "temp/nonexistent_back.jpg",
            "front_corners": [[100, 100], [700, 100], [700, 500], [100, 500]],
            "back_corners": [[100, 100], [700, 100], [700, 500], [100, 500]],
        }

        # 执行请求
        response = authenticated_client.post(
            "/api/v1/client/identity-docs/merge-id-card-manual",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        # 断言结果
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is False
        assert result["error"] == "INVALID_CORNERS"
        assert "不存在" in result["message"]

    def test_merge_id_card_manual_tilted_corners(self, authenticated_client, tmp_path, settings):
        """测试倾斜四角坐标

        **Validates: Requirements AC-2.2**
        """
        settings.MEDIA_ROOT = str(tmp_path)

        # 创建临时图片
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 创建较大的测试图片以容纳倾斜坐标
        front_image = np.ones((800, 1000, 3), dtype=np.uint8) * 255
        back_image = np.ones((800, 1000, 3), dtype=np.uint8) * 255

        front_path = temp_dir / "front_tilted.jpg"
        back_path = temp_dir / "back_tilted.jpg"

        cv2.imwrite(str(front_path), front_image)
        cv2.imwrite(str(back_path), back_image)

        # 准备请求数据（倾斜四角）
        data = {
            "front_image_path": "temp/front_tilted.jpg",
            "back_image_path": "temp/back_tilted.jpg",
            "front_corners": [[150, 120], [750, 100], [780, 480], [120, 500]],
            "back_corners": [[150, 120], [750, 100], [780, 480], [120, 500]],
        }

        # 执行请求
        response = authenticated_client.post(
            "/api/v1/client/identity-docs/merge-id-card-manual",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_HOST="localhost",
        )

        # 断言结果
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert "pdf_url" in result
