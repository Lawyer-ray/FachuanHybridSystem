"""基于 ONNX Model Zoo 的图片方向检测服务

使用 HuggingFace 预训练的 BEiT 模型：
- 模型来源: poutche/beit-image-orientation-onnx
- 输入: float32 [1, 3, 384, 384] (归一化: (x/255 - 0.5) / 0.5)
- 输出: float32 [1, 4] → 0°/90°/180°/270°

旋转公式: additional_rotation = (onnx_prediction - exif_rotation) % 360
前端 canvas 已通过 EXIF 显示正确方向，后端返回额外需要的旋转量。
"""

import io
import logging
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger("apps.image_rotation")

# 模型路径 - 优先使用 Fachuan 微调模型，回退到通用预训练模型
MODEL_DIR = Path(__file__).parent.parent.parent.parent / "models" / "orientation"
FACHUAN_MODEL_PATH = MODEL_DIR / "fachuan-orientation-classifier.onnx"
LEGACY_MODEL_PATH = MODEL_DIR / "beit-image-orientation.onnx"

# HuggingFace 模型 URL（用于自动下载通用模型）
MODEL_URL = "https://huggingface.co/poutche/beit-image-orientation-onnx/resolve/main/model.onnx"

# 方向标签
ORIENTATION_LABELS = {
    0: "0° (正常)",
    1: "90° (顺时针)",
    2: "180° (翻转)",
    3: "270° (逆时针)",
}

# 方向到旋转角度的映射
ORIENTATION_TO_ROTATION = {
    0: 0,
    1: 90,
    2: 180,
    3: 270,
}


class ONNXOrientationService:
    """基于 ONNX 模型的方向检测服务

    使用 HuggingFace 预训练的 BEiT 模型检测图片方向。
    模型在原始像素上运行，结合 EXIF 方向标签计算前端所需的旋转角度。
    置信度阈值: ≥0.85 时可自动旋转。
    """

    # 自动旋转的置信度阈值
    AUTO_ROTATE_THRESHOLD = 0.85

    def __init__(self, model_path: str | None = None, auto_download: bool = True):
        self._session = None
        self._model_path = model_path or self._resolve_model_path()
        self._auto_download = auto_download

    @staticmethod
    def _resolve_model_path() -> str:
        """解析模型路径：优先 Fachuan 微调模型，回退到通用预训练模型"""
        if FACHUAN_MODEL_PATH.exists():
            return str(FACHUAN_MODEL_PATH)
        return str(LEGACY_MODEL_PATH)

    @property
    def session(self):
        """懒加载 ONNX 推理会话"""
        if self._session is None:
            try:
                import onnxruntime as ort

                # 自动下载通用模型（如果两种模型都不存在）
                if self._auto_download and not Path(self._model_path).exists():
                    self._download_model()

                if not Path(self._model_path).exists():
                    logger.error(f"ONNX 模型文件不存在: {self._model_path}")
                    return None

                # 创建推理会话
                self._session = ort.InferenceSession(
                    self._model_path,
                    providers=["CPUExecutionProvider"],
                )
                model_type = "Fachuan 微调" if "fachuan" in self._model_path else "通用预训练"
                logger.info(f"ONNX 方向分类器加载成功 ({model_type}): {self._model_path}")
            except ImportError:
                logger.error("onnxruntime 未安装")
                return None
            except Exception as e:
                logger.error(f"ONNX 模型加载失败: {e}")
                return None
        return self._session

    def _download_model(self):
        """从 HuggingFace 下载模型"""
        import urllib.request

        MODEL_DIR.mkdir(parents=True, exist_ok=True)

        logger.info(f"下载 ONNX 方向分类器: {MODEL_URL}")
        try:
            urllib.request.urlretrieve(MODEL_URL, self._model_path)
            logger.info(f"模型下载成功: {self._model_path}")
        except Exception as e:
            logger.error(f"模型下载失败: {e}")

    def preprocess_image(self, image_data: bytes) -> np.ndarray:
        """预处理图片为模型输入格式

        在原始像素上运行（不做 EXIF 转正），让模型直接检测
        存储像素的旋转状态，便于与 EXIF 方向标签组合计算。

        BEiT 模型要求:
        - 输入: float32 [1, 3, 384, 384]
        - 归一化: (x/255 - 0.5) / 0.5
        """
        # 打开图片（不做 EXIF 转正，让模型在原始像素上检测方向）
        img = Image.open(io.BytesIO(image_data))

        # 转换为 RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        # 调整大小到 384x384（BEiT 模型要求）
        img = img.resize((384, 384), Image.Resampling.LANCZOS)

        # 转换为 numpy 数组
        img_array = np.array(img, dtype=np.float32)

        # HWC -> CHW
        img_array = img_array.transpose(2, 0, 1)

        # 归一化: (x/255 - 0.5) / 0.5
        img_array = (img_array / 255.0 - 0.5) / 0.5

        # 添加 batch 维度
        img_array = np.expand_dims(img_array, axis=0)

        return img_array

    def detect_orientation(self, image_data: bytes) -> dict[str, Any]:
        """检测图片方向

        在原始像素上运行 ONNX 方向分类器，并结合 EXIF 方向标签
        计算前端需要额外应用的旋转角度。

        前端 canvas 已通过 EXIF 显示正确方向。后端返回的旋转角度
        是在此基础上还需额外应用的旋转量：
          additional_rotation = (onnx_prediction - exif_rotation) % 360

        Args:
            image_data: 图片的字节数据

        Returns:
            包含 rotation, confidence, method, label 的字典
        """
        if not self.session:
            return {
                "rotation": 0,
                "confidence": 0,
                "method": "onnx_unavailable",
                "error": "ONNX 模型未加载",
            }

        try:
            # 获取原始图片尺寸和 EXIF 方向标签
            original_img = Image.open(io.BytesIO(image_data))
            stored_width, stored_height = original_img.size
            is_stored_landscape = stored_width > stored_height

            # 提取 EXIF 方向旋转角度（0/90/180/270）
            exif_rotation = self._get_exif_rotation(original_img)

            # 预处理图片（不做 EXIF 转正，让模型在原始像素上检测方向）
            input_data = self.preprocess_image(image_data)

            # 运行推理（BEiT 模型输入名为 "pixel_values"）
            inputs = {"pixel_values": input_data}
            outputs = self.session.run(None, inputs)

            # 解析输出
            logits = outputs[0]

            # Softmax
            exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
            probabilities = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)

            # 获取预测结果
            predicted_class = int(np.argmax(probabilities, axis=1)[0])
            confidence = float(probabilities[0][predicted_class])

            # ONNX 在原始像素上预测的旋转角度
            onnx_rotation = ORIENTATION_TO_ROTATION[predicted_class]
            label = ORIENTATION_LABELS[predicted_class]

            # 计算前端需要额外应用的旋转量
            # canvas 已通过 EXIF 显示正确方向，只需应用 ONNX 相对于 EXIF 的增量
            rotation = (onnx_rotation - exif_rotation) % 360

            logger.info(
                f"ONNX 方向检测: {label}, 置信度: {confidence:.4f}, "
                f"EXIF={exif_rotation}°, onnx={onnx_rotation}°, additional={rotation}°",
            )

            # 判断是否可以自动旋转
            # 置信度阈值
            high_confidence = confidence >= 0.85

            # 宽高比安全：存储为横向的图片不应被旋转为纵向（ONNX 可能将
            # EXIF 已修正的纵向图误判为需要 90°/270° 旋转）
            dimension_safe = not (is_stored_landscape and rotation in (90, 270))

            can_auto_rotate = high_confidence and dimension_safe and rotation != 0

            return {
                "rotation": rotation,
                "confidence": round(confidence, 4),
                "method": "onnx_classifier",
                "label": label,
                "can_auto_rotate": can_auto_rotate,
                "exif_orientation": exif_rotation,
                "probabilities": {
                    ORIENTATION_LABELS[i]: round(float(probabilities[0][i]), 4)
                    for i in range(4)
                },
            }

        except Exception as e:
            logger.error(f"ONNX 方向检测失败: {e}")
            return {
                "rotation": 0,
                "confidence": 0,
                "method": "onnx_error",
                "error": str(e),
            }

    @staticmethod
    def _get_exif_rotation(img: Image.Image) -> int:
        """从 EXIF 方向标签提取旋转角度（0/90/180/270）"""
        try:
            exif_data = img.getexif()
        except Exception:
            return 0

        # EXIF Orientation tag = 274 (0x0112)
        orientation = exif_data.get(274, 1)
        exif_map = {1: 0, 3: 180, 6: 90, 8: 270}
        return exif_map.get(orientation, 0)

    def detect_orientation_from_file(self, image_path: str) -> dict[str, Any]:
        """从文件检测图片方向"""
        with open(image_path, "rb") as f:
            image_data = f.read()
        return self.detect_orientation(image_data)


# 全局单例
_onnx_service: ONNXOrientationService | None = None


def get_onnx_orientation_service() -> ONNXOrientationService:
    """获取 ONNX 方向检测服务单例"""
    global _onnx_service
    if _onnx_service is None:
        _onnx_service = ONNXOrientationService()
    return _onnx_service
