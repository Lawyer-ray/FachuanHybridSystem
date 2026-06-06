"""
段落分类器
使用多级规则和上下文分析来识别段落层级
"""

import re
from typing import Tuple


class ParagraphClassifier:
    """段落分类器"""

    def classify(self, text: str, context: str = "") -> Tuple[int, str]:
        """
        分类段落层级

        Args:
            text: 段落文本
            context: 上下文（前后段落）

        Returns:
            (level, reason) 元组
        """
        # 1. 检测一级标题
        level = self._detect_level0(text)
        if level == 0:
            return 0, "一级标题"

        # 2. 检测二级标题
        level = self._detect_level1(text, context)
        if level == 1:
            return 1, "二级标题"

        # 3. 检测三级标题
        level = self._detect_level2(text, context)
        if level == 2:
            return 2, "三级标题"

        # 4. 默认不设置编号
        return -1, "正文"

    def _detect_level0(self, text: str) -> int:
        """检测一级标题"""
        # 一级标题特征：简短、明确的标题
        level0_keywords = [
            "服务内容", "服务范围", "费用", "保密义务", "责任限制",
            "免责条款", "合同期限", "违约责任", "服务响应时间",
            "争议解决", "其他约定"
        ]

        for keyword in level0_keywords:
            if keyword in text and len(text) < 20:
                return 0

        return -1

    def _detect_level1(self, text: str, context: str) -> int:
        """检测二级标题"""
        # 二级标题特征：具体的条款内容

        # 1. 以数字开头，描述具体事项
        if len(text) >= 2 and text[0].isdigit() and text[1] in "、.":
            if any(keyword in text for keyword in [
                "费用", "责任", "义务", "权利", "期限", "范围",
                "甲方", "乙方", "双方", "维护", "服务"
            ]):
                return 1

        # 2. 以"一、"、"二、"等开头
        if (len(text) >= 2 and text[0] in "一二三四五六七八九十" and text[1] == "、"):
            return 1

        # 3. 包含"乙方"、"甲方"等关键词（但不包括标题）
        # 只有当段落较长且包含这些关键词时才设置为二级标题
        if len(text) > 30 and any(keyword in text for keyword in ["乙方", "甲方", "双方"]):
            return 1

        return -1

    def _detect_level2(self, text: str, context: str) -> int:
        """检测三级标题"""
        # 三级标题特征：详细的操作说明

        # 1. 以"1."、"2."等开头
        if len(text) >= 2 and text[0].isdigit() and text[1] == ".":
            return 2

        # 2. 包含具体的操作或细节（但不包括标题）
        # 只有当段落较长且包含这些关键词时才设置为三级标题
        if len(text) > 30 and any(keyword in text for keyword in [
            "安装", "维修", "检测", "调试", "排查", "维护", "更新",
            "提供", "送修", "维修后", "若", "甲方", "乙方"
        ]):
            return 2

        return -1
