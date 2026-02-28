"""OCR 关键词分类服务 - 将图片分为对账单/出库单/收款凭证/其他"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("apps.evidence_sorting")

# 文件类型常量
TYPE_STATEMENT = "statement"  # 对账单
TYPE_DELIVERY = "delivery"  # 出库单/出仓单
TYPE_RECEIPT = "receipt"  # 收款凭证
TYPE_OTHER = "other"  # 其他

# 关键词权重表
_KEYWORDS: dict[str, list[str]] = {
    TYPE_STATEMENT: ["对账单", "对帐单", "对账", "月结", "月度汇总"],
    TYPE_DELIVERY: [
        "出库单", "出仓单", "出货单", "发货单", "送货单",
        "承运单", "提货单", "出库", "出仓",
    ],
    TYPE_RECEIPT: [
        "收款", "转账", "付款", "汇款", "收到", "到账",
        "银行回单", "电子回单", "交易成功", "支付成功",
        "中国农业银行", "中国工商银行", "中国建设银行",
        "中国银行", "招商银行", "微信支付", "支付宝",
    ],
}


@dataclass
class ClassifiedImage:
    """分类后的图片"""

    filename: str
    category: str  # statement / delivery / receipt / other
    ocr_text: str
    date: str | None = None  # YYYYMMDD
    amount: str | None = None  # 如 "65500"
    signed: bool | None = None  # 对账单是否签名
    confidence: float = 0.0
    image_data: str = ""  # base64
    rotation: int = 0


@dataclass
class ClassifyResult:
    """分类结果"""

    images: list[ClassifiedImage] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ClassifierService:
    """图片 OCR + 关键词分类"""

    def __init__(self) -> None:
        self._ocr_service: Any | None = None

    def _get_ocr_service(self) -> Any:
        if self._ocr_service is None:
            from apps.automation.services.image_rotation.orientation.service import (
                OrientationDetectionService,
            )
            self._ocr_service = OrientationDetectionService()
        return self._ocr_service

    def classify_images(
        self, images: list[dict[str, Any]]
    ) -> ClassifyResult:
        """
        批量 OCR + 分类

        Args:
            images: [{"filename": str, "data": str(base64)}]

        Returns:
            ClassifyResult
        """
        result = ClassifyResult()
        ocr_svc = self._get_ocr_service()

        for idx, img in enumerate(images):
            filename: str = img.get("filename", f"image_{idx}")
            data: str = img.get("data", "")
            try:
                # 去掉 data:image/xxx;base64, 前缀
                raw_data = data.split(",", 1)[-1] if "," in data else data
                image_bytes = base64.b64decode(raw_data)

                # OCR + 方向检测
                ocr_result = ocr_svc.detect_orientation_with_text(image_bytes)
                ocr_text: str = ocr_result.get("ocr_text", "")
                rotation: int = ocr_result.get("rotation", 0)
                confidence: float = ocr_result.get("confidence", 0.0)

                # 关键词分类
                category = self._classify_by_keywords(ocr_text, filename)

                # 提取日期和金额
                date = self._extract_date(ocr_text)
                amount = self._extract_amount(ocr_text)

                # 对账单检测签名
                signed: bool | None = None
                if category == TYPE_STATEMENT:
                    signed = self._detect_signed(ocr_text)

                result.images.append(ClassifiedImage(
                    filename=filename,
                    category=category,
                    ocr_text=ocr_text,
                    date=date,
                    amount=amount,
                    signed=signed,
                    confidence=confidence,
                    image_data=data,
                    rotation=rotation,
                ))
            except Exception as e:
                logger.warning("分类失败: %s - %s", filename, e)
                result.errors.append(f"{filename}: {e!s}")
                result.images.append(ClassifiedImage(
                    filename=filename,
                    category=TYPE_OTHER,
                    ocr_text="",
                    image_data=data,
                ))

        logger.info(
            "分类完成: %d 张图片, %d 个错误",
            len(result.images), len(result.errors),
        )
        return result

    def _classify_by_keywords(self, text: str, filename: str = "") -> str:
        """关键词匹配分类，返回匹配数最多的类型"""
        if not text:
            # OCR 识别不出文字的 PNG 文件，大概率是对账单截图
            if filename.lower().endswith(".png"):
                return TYPE_STATEMENT
            return TYPE_OTHER

        scores: dict[str, int] = {k: 0 for k in _KEYWORDS}
        for category, keywords in _KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[category] += 1

        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return TYPE_OTHER
        return best

    def _extract_date(self, text: str) -> str | None:
        """从 OCR 文本提取日期 → YYYYMMDD"""
        # 匹配 YYYY年MM月DD日 / YYYY-MM-DD / YYYY/MM/DD
        patterns = [
            r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
            r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
                return f"{y}{mo}{d}"
        return None

    def _extract_amount(self, text: str) -> str | None:
        """从 OCR 文本提取金额"""
        # 匹配 ¥123,456.78 / 123456.78元 / 金额:123456 等
        patterns = [
            r"[¥￥]\s*([\d,]+\.?\d*)",
            r"([\d,]+\.?\d*)\s*元",
            r"金额[：:]\s*([\d,]+\.?\d*)",
            r"合计[：:]\s*([\d,]+\.?\d*)",
            r"总计[：:]\s*([\d,]+\.?\d*)",
        ]
        amounts: list[float] = []
        for pat in patterns:
            for m in re.finditer(pat, text):
                try:
                    val = float(m.group(1).replace(",", ""))
                    amounts.append(val)
                except ValueError:
                    pass
        if amounts:
            # 返回最大金额
            best = max(amounts)
            # 保留小数（如果有）
            if best == int(best):
                return str(int(best))
            return str(best)
        return None

    def _detect_signed(self, text: str) -> bool:
        """检测对账单是否有签名痕迹（通过 OCR 文本中的签名相关关键词）"""
        sign_keywords = ["签名", "签章", "盖章", "确认", "签字"]
        # 如果 OCR 文本中有大量手写体识别（置信度低的文字），可能有签名
        # 简单策略：检查关键词
        return any(kw in text for kw in sign_keywords)
