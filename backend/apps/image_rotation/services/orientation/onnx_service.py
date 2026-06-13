"""基于 ConvNeXtV2-Atto 的图片方向检测服务

使用 Fachuan 微调的 ConvNeXtV2-Atto 方向分类 ONNX 模型：
- 模型来源: ml-training/train_model.py 微调导出
- 输入: float32 [1, 3, 224, 224] (ImageNet 归一化)
- 输出: float32 [1, 4] → 0°/90°/180°/270°

推理流程: EXIF 转正 → ONNX 分类 → 返回旋转角度
模型在 EXIF 转正后的像素上训练，推理时需保持一致。
"""

import io
import logging
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger("apps.image_rotation")

# 模型路径（仅使用微调模型）
MODEL_DIR = Path(__file__).parent.parent.parent.parent / "models" / "orientation"
MODEL_PATH = MODEL_DIR / "fachuan-orientation-classifier.onnx"

# 方向标签（与 ImageFolder 目录排序一致: 0, 180, 270, 90）
ORIENTATION_LABELS = {
    0: "0° (正常)",
    1: "180° (翻转)",
    2: "270° (逆时针)",
    3: "90° (顺时针)",
}

# 方向到旋转角度的映射
# ImageFolder 按目录名排序: '0'→0, '180'→1, '270'→2, '90'→3
# 训练时用 PIL rotate(angle) 逆时针旋转，后端用 rotate(-angle) 顺时针复原
ORIENTATION_TO_ROTATION = {
    0: 0,
    1: 180,
    2: -90,
    3: -270,
}


class ONNXOrientationService:
    """基于微调 BEiT 的方向检测服务

    推理时先 EXIF 转正，再运行 ONNX 分类器。
    置信度阈值: ≥0.65 时可自动旋转（4分类随机基线 0.25，0.65 已有充足置信余量）。
    """

    # 自动旋转的置信度阈值（4分类随机基线 0.25，0.65 以上视为有把握）
    AUTO_ROTATE_THRESHOLD = 0.65

    def __init__(self, model_path: str | None = None):
        self._session = None
        self._model_path = model_path or str(MODEL_PATH)

    @property
    def session(self):
        """懒加载 ONNX 推理会话"""
        if self._session is None:
            try:
                import onnxruntime as ort

                if not Path(self._model_path).exists():
                    logger.error(
                        f"ONNX 微调模型不存在: {self._model_path}，"
                        "请运行 ml-training/train_model.py 训练或从 HuggingFace Hub 下载"
                    )
                    return None

                self._session = ort.InferenceSession(
                    self._model_path,
                    providers=["CPUExecutionProvider"],
                )
                logger.info(f"ONNX 方向分类器加载成功: {self._model_path}")
            except ImportError:
                logger.error("onnxruntime 未安装")
                return None
            except Exception as e:
                logger.error(f"ONNX 模型加载失败: {e}")
                return None
        return self._session

    def preprocess_image(self, image_data: bytes) -> np.ndarray:
        """预处理图片为模型输入格式

        先应用 EXIF 转正，使像素排列与训练时一致，再缩放和归一化。

        ConvNeXtV2 模型要求:
        - 输入: float32 [1, 3, 224, 224]
        - 归一化: ImageNet 标准 (mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        """
        img = Image.open(io.BytesIO(image_data))

        # EXIF 转正：与训练时 prepare_data.py 的 ImageOps.exif_transpose() 保持一致
        img = ImageOps.exif_transpose(img) or img

        # 转换为 RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        # 调整大小到 224x224（ConvNeXtV2 模型要求）
        img = img.resize((224, 224), Image.Resampling.LANCZOS)

        # 转换为 numpy 数组
        img_array = np.array(img, dtype=np.float32)

        # HWC -> CHW
        img_array = img_array.transpose(2, 0, 1)

        # ImageNet 归一化: (x/255 - mean) / std
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)
        img_array = (img_array / 255.0 - mean) / std

        # 添加 batch 维度
        img_array = np.expand_dims(img_array, axis=0)

        return img_array

    def detect_orientation(self, image_data: bytes) -> dict[str, Any]:
        """检测图片方向

        EXIF 转正后运行 ONNX 分类器，返回使图片正向所需的旋转角度。

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
            # 预处理图片（EXIF 转正 + 缩放归一化）
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

            # ONNX 预测的旋转角度（EXIF 转正后像素上的预测，直接作为旋转角度）
            rotation = ORIENTATION_TO_ROTATION[predicted_class]
            label = ORIENTATION_LABELS[predicted_class]

            logger.info(
                f"ONNX 方向检测: {label}, 置信度: {confidence:.4f}, rotation={rotation}°",
            )

            # 判断是否可以自动旋转
            high_confidence = confidence >= self.AUTO_ROTATE_THRESHOLD

            can_auto_rotate = high_confidence and rotation != 0

            return {
                "rotation": rotation,
                "confidence": round(confidence, 4),
                "method": "onnx_classifier",
                "label": label,
                "can_auto_rotate": can_auto_rotate,
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
