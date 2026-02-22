"""
身份证合并服务单元测试

测试 IdCardMergeService 的透视变换功能
"""

import numpy as np
import pytest

from apps.client.services.id_card_merge_service import IdCardMergeService


class TestPerspectiveTransform:
    """透视变换测试

    验证正确性属性 P1:
    - 输出图片的宽高比应接近 1.58:1 (85.6/54)
    - 允许误差 ±5%
    """

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = IdCardMergeService()
        # 身份证标准宽高比
        self.expected_ratio = 85.6 / 54.0  # ≈ 1.5852
        # 允许误差 ±5%
        self.tolerance = 0.05

    def _create_test_image(self, width: int, height: int) -> np.ndarray:
        """创建测试图像"""
        # 创建白色背景图像 (BGR 格式)
        image = np.ones((height, width, 3), dtype=np.uint8) * 255
        return image

    def _create_rectangle_corners(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> np.ndarray:
        """创建矩形四角坐标 (左上、右上、右下、左下)"""
        return np.array(
            [
                [x, y],  # 左上
                [x + width, y],  # 右上
                [x + width, y + height],  # 右下
                [x, y + height],  # 左下
            ],
            dtype=np.float32,
        )

    def _assert_aspect_ratio(self, image: np.ndarray):
        """断言图像宽高比在允许范围内"""
        height, width = image.shape[:2]
        actual_ratio = width / height

        min_ratio = self.expected_ratio * (1 - self.tolerance)
        max_ratio = self.expected_ratio * (1 + self.tolerance)

        assert min_ratio <= actual_ratio <= max_ratio, (
            f"宽高比 {actual_ratio:.4f} 不在允许范围 [{min_ratio:.4f}, {max_ratio:.4f}] 内"
        )

    def test_perspective_transform_standard_rectangle(self):
        """测试标准矩形的透视变换

        **Validates: Requirements P1**
        输入一个标准矩形区域，验证输出宽高比接近 1.58:1
        """
        # 创建 1000x800 的测试图像
        image = self._create_test_image(1000, 800)

        # 定义一个标准矩形区域 (模拟身份证)
        corners = self._create_rectangle_corners(100, 100, 600, 380)

        # 执行透视变换
        result = self.service._perspective_transform(image, corners)

        # 验证输出不为空
        assert result is not None
        assert result.size > 0

        # 验证宽高比
        self._assert_aspect_ratio(result)

    def test_perspective_transform_tilted_rectangle(self):
        """测试倾斜矩形的透视变换

        **Validates: Requirements P1**
        输入一个倾斜的四边形，验证输出宽高比接近 1.58:1
        """
        # 创建 1200x900 的测试图像
        image = self._create_test_image(1200, 900)

        # 定义一个倾斜的四边形 (模拟倾斜拍摄的身份证)
        corners = np.array(
            [
                [150, 120],  # 左上
                [750, 100],  # 右上
                [780, 480],  # 右下
                [120, 500],  # 左下
            ],
            dtype=np.float32,
        )

        # 执行透视变换
        result = self.service._perspective_transform(image, corners)

        # 验证输出不为空
        assert result is not None
        assert result.size > 0

        # 验证宽高比
        self._assert_aspect_ratio(result)

    def test_perspective_transform_trapezoid(self):
        """测试梯形的透视变换

        **Validates: Requirements P1**
        输入一个梯形区域 (模拟透视畸变)，验证输出宽高比接近 1.58:1
        """
        # 创建 1000x800 的测试图像
        image = self._create_test_image(1000, 800)

        # 定义一个梯形 (上窄下宽，模拟从上方拍摄)
        corners = np.array(
            [
                [200, 150],  # 左上
                [600, 150],  # 右上
                [700, 500],  # 右下
                [100, 500],  # 左下
            ],
            dtype=np.float32,
        )

        # 执行透视变换
        result = self.service._perspective_transform(image, corners)

        # 验证输出不为空
        assert result is not None
        assert result.size > 0

        # 验证宽高比
        self._assert_aspect_ratio(result)

    def test_perspective_transform_small_region(self):
        """测试小区域的透视变换

        **Validates: Requirements P1**
        输入一个较小的区域，验证输出有最小尺寸保证且宽高比正确
        """
        # 创建 500x400 的测试图像
        image = self._create_test_image(500, 400)

        # 定义一个较小的矩形区域
        corners = self._create_rectangle_corners(50, 50, 200, 127)

        # 执行透视变换
        result = self.service._perspective_transform(image, corners)

        # 验证输出不为空
        assert result is not None
        assert result.size > 0

        # 验证最小尺寸
        height, width = result.shape[:2]
        assert width >= 400, f"输出宽度 {width} 小于最小值 400"

        # 验证宽高比
        self._assert_aspect_ratio(result)

    def test_perspective_transform_large_region(self):
        """测试大区域的透视变换

        **Validates: Requirements P1**
        输入一个较大的区域，验证输出宽高比正确
        """
        # 创建 2000x1500 的测试图像
        image = self._create_test_image(2000, 1500)

        # 定义一个较大的矩形区域
        corners = self._create_rectangle_corners(100, 100, 1600, 1012)

        # 执行透视变换
        result = self.service._perspective_transform(image, corners)

        # 验证输出不为空
        assert result is not None
        assert result.size > 0

        # 验证宽高比
        self._assert_aspect_ratio(result)

    def test_perspective_transform_preserves_color(self):
        """测试透视变换保持颜色

        验证变换后图像仍为 BGR 格式
        """
        # 创建彩色测试图像
        image = self._create_test_image(800, 600)
        # 在中心区域填充红色
        image[200:400, 200:600] = [0, 0, 255]  # BGR 红色

        corners = self._create_rectangle_corners(100, 100, 600, 380)

        # 执行透视变换
        result = self.service._perspective_transform(image, corners)

        # 验证输出为 3 通道图像
        assert len(result.shape) == 3
        assert result.shape[2] == 3

    def test_perspective_transform_with_rotated_card(self):
        """测试旋转卡片的透视变换

        **Validates: Requirements P1**
        模拟身份证被旋转放置的情况
        """
        # 创建 1000x1000 的测试图像
        image = self._create_test_image(1000, 1000)

        # 定义一个旋转约 15 度的四边形
        corners = np.array(
            [
                [200, 300],  # 左上
                [700, 200],  # 右上
                [750, 550],  # 右下
                [250, 650],  # 左下
            ],
            dtype=np.float32,
        )

        # 执行透视变换
        result = self.service._perspective_transform(image, corners)

        # 验证输出不为空
        assert result is not None
        assert result.size > 0

        # 验证宽高比
        self._assert_aspect_ratio(result)


class TestOrderCorners:
    """四角排序测试

    验证正确性属性 P3:
    - 四角顺序：左上 → 右上 → 右下 → 左下
    """

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = IdCardMergeService()

    def test_order_corners_standard(self):
        """测试标准顺序的四角排序"""
        # 已经是正确顺序的四角
        corners = np.array(
            [
                [100, 100],  # 左上
                [500, 100],  # 右上
                [500, 400],  # 右下
                [100, 400],  # 左下
            ],
            dtype=np.float32,
        )

        result = self.service._order_corners(corners)

        # 验证顺序正确
        assert result[0][0] < result[1][0]  # 左上 x < 右上 x
        assert result[0][1] < result[3][1]  # 左上 y < 左下 y
        assert result[1][0] > result[0][0]  # 右上 x > 左上 x
        assert result[2][1] > result[1][1]  # 右下 y > 右上 y

    def test_order_corners_shuffled(self):
        """测试乱序四角的排序"""
        # 乱序的四角
        corners = np.array(
            [
                [500, 400],  # 右下
                [100, 100],  # 左上
                [100, 400],  # 左下
                [500, 100],  # 右上
            ],
            dtype=np.float32,
        )

        result = self.service._order_corners(corners)

        # 验证排序后的顺序
        # 左上应该是 x+y 最小的点
        assert np.allclose(result[0], [100, 100])
        # 右上应该是 x-y 最大的点
        assert np.allclose(result[1], [500, 100])
        # 右下应该是 x+y 最大的点
        assert np.allclose(result[2], [500, 400])
        # 左下应该是 x-y 最小的点
        assert np.allclose(result[3], [100, 400])

    def test_order_corners_tilted(self):
        """测试倾斜四边形的四角排序"""
        # 倾斜的四边形
        corners = np.array(
            [
                [150, 120],  # 左上
                [750, 100],  # 右上
                [780, 480],  # 右下
                [120, 500],  # 左下
            ],
            dtype=np.float32,
        )

        result = self.service._order_corners(corners)

        # 验证左上角 (x+y 最小)
        sums = corners[:, 0] + corners[:, 1]
        expected_top_left = corners[np.argmin(sums)]
        assert np.allclose(result[0], expected_top_left)

        # 验证右下角 (x+y 最大)
        expected_bottom_right = corners[np.argmax(sums)]
        assert np.allclose(result[2], expected_bottom_right)


class TestGeneratePdf:
    """PDF 生成测试

    验证正确性属性 P2:
    - 输出 PDF 为标准 A4 尺寸
    - 身份证图片居中显示
    """

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = IdCardMergeService()

    def _create_test_image(self, width: int, height: int) -> np.ndarray:
        """创建测试图像"""
        # 创建白色背景图像 (BGR 格式)
        image = np.ones((height, width, 3), dtype=np.uint8) * 255
        return image

    def _create_id_card_image(self) -> np.ndarray:
        """创建模拟身份证图像 (标准比例 1.58:1)"""
        # 身份证标准比例约 1.58:1
        width = 856
        height = 540
        image = self._create_test_image(width, height)
        # 添加一些颜色以区分正反面
        image[100:200, 100:300] = [255, 0, 0]  # BGR 蓝色区域
        return image

    def test_generate_pdf_creates_file(self, tmp_path, settings):
        """测试 PDF 文件生成

        **Validates: Requirements P2**
        验证 _generate_pdf 方法能正确生成 PDF 文件
        """
        # 设置临时 MEDIA_ROOT
        settings.MEDIA_ROOT = str(tmp_path)

        # 创建测试图像
        front_image = self._create_id_card_image()
        back_image = self._create_id_card_image()
        # 反面用不同颜色
        back_image[100:200, 100:300] = [0, 255, 0]  # BGR 绿色区域

        # 生成 PDF
        pdf_path = self.service._generate_pdf(front_image, back_image)

        # 验证返回路径格式
        assert pdf_path.startswith("id_card_merged/")
        assert pdf_path.endswith(".pdf")

        # 验证文件存在
        full_path = tmp_path / pdf_path
        assert full_path.exists(), f"PDF 文件不存在: {full_path}"

        # 验证文件大小 > 0
        assert full_path.stat().st_size > 0

    def test_generate_pdf_a4_size(self, tmp_path, settings):
        """测试 PDF 为 A4 尺寸

        **Validates: Requirements P2**
        验证生成的 PDF 为标准 A4 尺寸 (210mm × 297mm)
        """
        import pikepdf
        from reportlab.lib.pagesizes import A4

        # 设置临时 MEDIA_ROOT
        settings.MEDIA_ROOT = str(tmp_path)

        # 创建测试图像
        front_image = self._create_id_card_image()
        back_image = self._create_id_card_image()

        # 生成 PDF
        pdf_path = self.service._generate_pdf(front_image, back_image)
        full_path = tmp_path / pdf_path

        # 读取 PDF 并验证尺寸
        with pikepdf.open(str(full_path)) as pdf:
            page = pdf.pages[0]
            mediabox = page.mediabox

            # 获取页面尺寸 (points)
            page_width = float(mediabox[2]) - float(mediabox[0])
            page_height = float(mediabox[3]) - float(mediabox[1])

        # A4 尺寸 (points): 595.27 x 841.89
        expected_width, expected_height = A4

        # 允许 1 point 的误差
        assert abs(page_width - expected_width) < 1, f"PDF 宽度 {page_width} 不等于 A4 宽度 {expected_width}"
        assert abs(page_height - expected_height) < 1, f"PDF 高度 {page_height} 不等于 A4 高度 {expected_height}"

    def test_generate_pdf_cleans_temp_files(self, tmp_path, settings):
        """测试临时文件清理

        验证 PDF 生成后临时图片文件被清理
        """
        # 设置临时 MEDIA_ROOT
        settings.MEDIA_ROOT = str(tmp_path)

        # 创建测试图像
        front_image = self._create_id_card_image()
        back_image = self._create_id_card_image()

        # 生成 PDF
        self.service._generate_pdf(front_image, back_image)

        # 检查临时目录中没有 front_pdf_ 或 back_pdf_ 开头的文件
        temp_dir = tmp_path / "temp"
        if temp_dir.exists():
            temp_files = list(temp_dir.glob("*_pdf_*.jpg"))
            assert len(temp_files) == 0, f"临时文件未清理: {[f.name for f in temp_files]}"

    def test_generate_pdf_unique_filenames(self, tmp_path, settings):
        """测试生成唯一文件名

        验证多次调用生成不同的文件名
        """
        # 设置临时 MEDIA_ROOT
        settings.MEDIA_ROOT = str(tmp_path)

        # 创建测试图像
        front_image = self._create_id_card_image()
        back_image = self._create_id_card_image()

        # 生成多个 PDF
        pdf_paths = []
        for _ in range(3):
            pdf_path = self.service._generate_pdf(front_image, back_image)
            pdf_paths.append(pdf_path)

        # 验证所有路径都不同
        assert len(set(pdf_paths)) == 3, "生成的 PDF 文件名不唯一"

    def test_generate_pdf_output_directory_created(self, tmp_path, settings):
        """测试输出目录自动创建

        验证 id_card_merged 目录不存在时会自动创建
        """
        # 设置临时 MEDIA_ROOT (确保目录不存在)
        settings.MEDIA_ROOT = str(tmp_path)

        # 确保输出目录不存在
        output_dir = tmp_path / "id_card_merged"
        assert not output_dir.exists()

        # 创建测试图像
        front_image = self._create_id_card_image()
        back_image = self._create_id_card_image()

        # 生成 PDF
        self.service._generate_pdf(front_image, back_image)

        # 验证目录已创建
        assert output_dir.exists()
        assert output_dir.is_dir()


class TestValidateCorners:
    """四角坐标验证测试

    验证正确性属性 P3:
    - 检测到的四角应形成凸四边形
    - 四角顺序：左上 → 右上 → 右下 → 左下
    """

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = IdCardMergeService()

    def test_validate_corners_valid_rectangle(self):
        """测试有效矩形四角

        **Validates: Requirements P3**
        """
        corners = [[100, 100], [500, 100], [500, 400], [100, 400]]
        result = self.service._validate_corners(corners)
        assert result is None, f"有效矩形应通过验证，但返回: {result}"

    def test_validate_corners_valid_convex_quadrilateral(self):
        """测试有效凸四边形

        **Validates: Requirements P3**
        """
        # 倾斜的凸四边形
        corners = [[150, 120], [750, 100], [780, 480], [120, 500]]
        result = self.service._validate_corners(corners)
        assert result is None, f"有效凸四边形应通过验证，但返回: {result}"

    def test_validate_corners_invalid_point_count(self):
        """测试点数不足

        **Validates: Requirements P3**
        """
        # 只有 3 个点
        corners = [[100, 100], [500, 100], [500, 400]]
        result = self.service._validate_corners(corners)
        assert result is not None
        assert "4 个角点" in result

    def test_validate_corners_empty_list(self):
        """测试空列表"""
        result = self.service._validate_corners([])
        assert result is not None
        assert "4 个角点" in result

    def test_validate_corners_none(self):
        """测试 None 输入"""
        result = self.service._validate_corners(None)
        assert result is not None
        assert "4 个角点" in result

    def test_validate_corners_invalid_point_format(self):
        """测试无效点格式"""
        # 点只有一个坐标
        corners = [[100], [500, 100], [500, 400], [100, 400]]
        result = self.service._validate_corners(corners)
        assert result is not None
        assert "格式无效" in result

    def test_validate_corners_negative_coordinates(self):
        """测试负坐标"""
        corners = [[-100, 100], [500, 100], [500, 400], [100, 400]]
        result = self.service._validate_corners(corners)
        assert result is not None
        assert "负数" in result

    def test_validate_corners_non_numeric(self):
        """测试非数字坐标"""
        corners = [["abc", 100], [500, 100], [500, 400], [100, 400]]
        result = self.service._validate_corners(corners)
        assert result is not None
        assert "数字" in result

    def test_validate_corners_concave_quadrilateral(self):
        """测试凹四边形 (非凸)

        **Validates: Requirements P3**
        凹四边形应该验证失败
        """
        # 凹四边形 (一个点凹进去)
        corners = [[100, 100], [500, 100], [300, 250], [100, 400]]
        result = self.service._validate_corners(corners)
        assert result is not None
        assert "凸四边形" in result

    def test_validate_corners_self_intersecting(self):
        """测试自相交四边形

        **Validates: Requirements P3**
        注意：由于 _validate_corners 会先调用 _order_corners 对点进行排序，
        蝴蝶结形状的点会被重新排序为凸四边形，因此这个测试验证的是
        排序后仍然是自相交的情况（实际上很难构造）。

        这里我们测试一个更明确的凹四边形案例。
        """
        # 凹四边形 - 一个点明显凹进去
        corners = [[0, 0], [400, 0], [200, 100], [0, 200]]
        result = self.service._validate_corners(corners)
        assert result is not None
        assert "凸四边形" in result


class TestIsConvexQuadrilateral:
    """凸四边形判断测试

    验证正确性属性 P3:
    - 检测到的四角应形成凸四边形
    """

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = IdCardMergeService()

    def test_is_convex_rectangle(self):
        """测试矩形是凸四边形"""
        corners = np.array([[100, 100], [500, 100], [500, 400], [100, 400]], dtype=np.float32)
        assert self.service._is_convex_quadrilateral(corners) is True

    def test_is_convex_parallelogram(self):
        """测试平行四边形是凸四边形"""
        corners = np.array([[150, 100], [550, 100], [500, 400], [100, 400]], dtype=np.float32)
        assert self.service._is_convex_quadrilateral(corners) is True

    def test_is_convex_trapezoid(self):
        """测试梯形是凸四边形"""
        corners = np.array([[200, 100], [400, 100], [500, 400], [100, 400]], dtype=np.float32)
        assert self.service._is_convex_quadrilateral(corners) is True

    def test_is_not_convex_concave(self):
        """测试凹四边形不是凸四边形"""
        # 凹四边形 - 第三个点凹进去
        corners = np.array([[100, 100], [500, 100], [300, 250], [100, 400]], dtype=np.float32)
        assert self.service._is_convex_quadrilateral(corners) is False

    def test_is_not_convex_self_intersecting(self):
        """测试自相交四边形不是凸四边形"""
        # 蝴蝶结形状
        corners = np.array([[100, 100], [500, 400], [500, 100], [100, 400]], dtype=np.float32)
        assert self.service._is_convex_quadrilateral(corners) is False

    def test_is_not_convex_wrong_point_count(self):
        """测试点数不对返回 False"""
        corners = np.array([[100, 100], [500, 100], [500, 400]], dtype=np.float32)
        assert self.service._is_convex_quadrilateral(corners) is False


class TestMergeIdCardManual:
    """手动合并测试

    验证 AC-2.2: 支持用户提供四角坐标进行手动矫正
    验证 AC-2.3: 手动模式下同样输出标准 PDF
    """

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = IdCardMergeService()

    def _create_test_image(self, width: int, height: int) -> np.ndarray:
        """创建测试图像"""
        import cv2

        image = np.ones((height, width, 3), dtype=np.uint8) * 255
        # 添加一些内容使图像更真实
        cv2.rectangle(image, (50, 50), (width - 50, height - 50), (200, 200, 200), 2)
        return image

    def test_merge_id_card_manual_success(self, tmp_path, settings):
        """测试手动合并成功

        **Validates: Requirements AC-2.2, AC-2.3**
        """
        import cv2

        # 设置临时 MEDIA_ROOT
        settings.MEDIA_ROOT = str(tmp_path)

        # 创建临时目录
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 创建测试图片
        front_image = self._create_test_image(800, 600)
        back_image = self._create_test_image(800, 600)

        front_path = temp_dir / "front_test.jpg"
        back_path = temp_dir / "back_test.jpg"

        cv2.imwrite(str(front_path), front_image)
        cv2.imwrite(str(back_path), back_image)

        # 定义有效的四角坐标
        front_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]
        back_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]

        # 执行手动合并
        result = self.service.merge_id_card_manual(
            front_image_path="temp/front_test.jpg",
            back_image_path="temp/back_test.jpg",
            front_corners=front_corners,
            back_corners=back_corners,
        )

        # 验证成功
        assert result["success"] is True
        assert "pdf_path" in result
        assert "pdf_url" in result
        assert result["pdf_path"].startswith("id_card_merged/")
        assert result["pdf_path"].endswith(".pdf")

        # 验证 PDF 文件存在
        pdf_full_path = tmp_path / result["pdf_path"]
        assert pdf_full_path.exists()

    def test_merge_id_card_manual_with_media_prefix(self, tmp_path, settings):
        """测试带 /media/ 前缀的路径

        **Validates: Requirements AC-2.2**
        """
        import cv2

        settings.MEDIA_ROOT = str(tmp_path)

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        front_image = self._create_test_image(800, 600)
        back_image = self._create_test_image(800, 600)

        front_path = temp_dir / "front_test2.jpg"
        back_path = temp_dir / "back_test2.jpg"

        cv2.imwrite(str(front_path), front_image)
        cv2.imwrite(str(back_path), back_image)

        front_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]
        back_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]

        # 使用带 /media/ 前缀的路径
        result = self.service.merge_id_card_manual(
            front_image_path="/media/temp/front_test2.jpg",
            back_image_path="/media/temp/back_test2.jpg",
            front_corners=front_corners,
            back_corners=back_corners,
        )

        assert result["success"] is True

    def test_merge_id_card_manual_invalid_front_corners(self, tmp_path, settings):
        """测试正面四角坐标无效

        **Validates: Requirements INVALID_CORNERS error**
        """
        settings.MEDIA_ROOT = str(tmp_path)

        # 无效的四角坐标 (只有 3 个点)
        front_corners = [[100, 100], [700, 100], [700, 500]]
        back_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]

        result = self.service.merge_id_card_manual(
            front_image_path="temp/front.jpg",
            back_image_path="temp/back.jpg",
            front_corners=front_corners,
            back_corners=back_corners,
        )

        assert result["success"] is False
        assert result["error"] == "INVALID_CORNERS"
        assert "正面" in result["message"]

    def test_merge_id_card_manual_invalid_back_corners(self, tmp_path, settings):
        """测试反面四角坐标无效

        **Validates: Requirements INVALID_CORNERS error**
        """
        import cv2

        settings.MEDIA_ROOT = str(tmp_path)

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        front_image = self._create_test_image(800, 600)
        front_path = temp_dir / "front_test3.jpg"
        cv2.imwrite(str(front_path), front_image)

        # 正面有效，反面无效 (凹四边形)
        front_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]
        back_corners = [[100, 100], [700, 100], [400, 300], [100, 500]]

        result = self.service.merge_id_card_manual(
            front_image_path="temp/front_test3.jpg",
            back_image_path="temp/back.jpg",
            front_corners=front_corners,
            back_corners=back_corners,
        )

        assert result["success"] is False
        assert result["error"] == "INVALID_CORNERS"
        assert "反面" in result["message"]

    def test_merge_id_card_manual_front_image_not_found(self, tmp_path, settings):
        """测试正面图片不存在"""
        settings.MEDIA_ROOT = str(tmp_path)

        front_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]
        back_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]

        result = self.service.merge_id_card_manual(
            front_image_path="temp/nonexistent_front.jpg",
            back_image_path="temp/nonexistent_back.jpg",
            front_corners=front_corners,
            back_corners=back_corners,
        )

        assert result["success"] is False
        assert result["error"] == "INVALID_CORNERS"
        assert "正面图片不存在" in result["message"]

    def test_merge_id_card_manual_back_image_not_found(self, tmp_path, settings):
        """测试反面图片不存在"""
        import cv2

        settings.MEDIA_ROOT = str(tmp_path)

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 只创建正面图片
        front_image = self._create_test_image(800, 600)
        front_path = temp_dir / "front_only.jpg"
        cv2.imwrite(str(front_path), front_image)

        front_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]
        back_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]

        result = self.service.merge_id_card_manual(
            front_image_path="temp/front_only.jpg",
            back_image_path="temp/nonexistent_back.jpg",
            front_corners=front_corners,
            back_corners=back_corners,
        )

        assert result["success"] is False
        assert result["error"] == "INVALID_CORNERS"
        assert "反面图片不存在" in result["message"]

    def test_merge_id_card_manual_cleans_temp_files(self, tmp_path, settings):
        """测试临时文件清理

        验证合并成功后临时图片被清理
        """
        import cv2

        settings.MEDIA_ROOT = str(tmp_path)

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        front_image = self._create_test_image(800, 600)
        back_image = self._create_test_image(800, 600)

        front_path = temp_dir / "front_cleanup.jpg"
        back_path = temp_dir / "back_cleanup.jpg"

        cv2.imwrite(str(front_path), front_image)
        cv2.imwrite(str(back_path), back_image)

        front_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]
        back_corners = [[100, 100], [700, 100], [700, 500], [100, 500]]

        # 执行合并
        result = self.service.merge_id_card_manual(
            front_image_path="temp/front_cleanup.jpg",
            back_image_path="temp/back_cleanup.jpg",
            front_corners=front_corners,
            back_corners=back_corners,
        )

        assert result["success"] is True

        # 验证临时文件已被清理
        assert not front_path.exists(), "正面临时图片应被清理"
        assert not back_path.exists(), "反面临时图片应被清理"

    def test_merge_id_card_manual_tilted_corners(self, tmp_path, settings):
        """测试倾斜四角坐标

        **Validates: Requirements AC-2.2**
        验证可以处理倾斜的四角坐标
        """
        import cv2

        settings.MEDIA_ROOT = str(tmp_path)

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        front_image = self._create_test_image(1000, 800)
        back_image = self._create_test_image(1000, 800)

        front_path = temp_dir / "front_tilted.jpg"
        back_path = temp_dir / "back_tilted.jpg"

        cv2.imwrite(str(front_path), front_image)
        cv2.imwrite(str(back_path), back_image)

        # 倾斜的四角坐标
        front_corners = [[150, 120], [750, 100], [780, 480], [120, 500]]
        back_corners = [[150, 120], [750, 100], [780, 480], [120, 500]]

        result = self.service.merge_id_card_manual(
            front_image_path="temp/front_tilted.jpg",
            back_image_path="temp/back_tilted.jpg",
            front_corners=front_corners,
            back_corners=back_corners,
        )

        assert result["success"] is True
        assert "pdf_path" in result
