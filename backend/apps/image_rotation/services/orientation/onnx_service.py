"""基于 ONNX Model Zoo 的图片方向检测服务

使用 HuggingFace 预训练的 BEiT 模型：
- 模型来源: poutche/beit-image-orientation-onnx
- 输入: float32 [1, 3, 384, 384] (归一化: (x/255 - 0.5) / 0.5)
- 输出: float32 [1, 4] → 0°/90°/180°/270°
- 置信度阈值: ≥0.99 时可自动旋转
"""

import io
import logging
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger("apps.image_rotation")

# 模型路径 - 使用 HuggingFace 下载的预训练模型
MODEL_DIR = Path(__file__).parent.parent.parent.parent / "models" / "orientation"
MODEL_PATH = MODEL_DIR / "beit-image-orientation.onnx"

# HuggingFace 模型 URL（用于自动下载）
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
    置信度阈值: ≥0.99 时可自动旋转。
    """

    # 自动旋转的置信度阈值
    AUTO_ROTATE_THRESHOLD = 0.99

    def __init__(self, model_path: str | None = None, auto_download: bool = True):
        self._session = None
        self._model_path = model_path or str(MODEL_PATH)
        self._auto_download = auto_download

    @property
    def session(self):
        """懒加载 ONNX 推理会话"""
        if self._session is None:
            try:
                import onnxruntime as ort

                # 自动下载模型（如果启用）
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
                logger.info(f"ONNX 方向分类器加载成功: {self._model_path}")
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

        BEiT 模型要求:
        - 输入: float32 [1, 3, 384, 384]
        - 归一化: (x/255 - 0.5) / 0.5
        """
        # 打开图片
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
            # 预处理图片
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

            # 获取对应的旋转角度
            rotation = ORIENTATION_TO_ROTATION[predicted_class]
            label = ORIENTATION_LABELS[predicted_class]

            logger.info(
                f"ONNX 方向检测: {label}, 置信度: {confidence:.4f}",
            )

            # 判断是否可以自动旋转
            can_auto_rotate = confidence >= self.AUTO_ROTATE_THRESHOLD and rotation != 0

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
