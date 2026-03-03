from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from apps.core.llm.service import LLMService

logger = logging.getLogger(__name__)

_REVIEW_FRAMEWORK = """\
## 一、基础审查
1. 文本准确性：
- 检查所有关键词、术语拼写是否正确
- 核对所有数字、金额、比例是否准确（特别注意大小写金额是否一致）
- 检查日期表述是否精确（避免使用"近期"、"尽快"等模糊词语）
2. 格式规范性：
- 检查标点符号使用是否规范
- 审核条款编号是否有序连贯，是否存在重复编号
- 检查排版是否整洁，有无明显格式错误
- 确认签署处是否留有足够空间
3. 语言表述清晰性：
- 检查是否存在语法错误或表述不清的句子
- 识别有歧义或模糊的描述，特别是关于时间、数量、质量的表述
- 检查专业术语使用是否准确
4. 文本一致性：
- 检查同一概念在合同不同部分的称谓是否一致（如产品名称、型号等）
- 核对合同内部引用条款编号是否准确
- 确认前后条款是否存在逻辑冲突
- 检查附件与正文是否一致

## 二、合同主体审查
1. 主体信息完整性：
- 验证是否包含主体的全称、统一社会信用代码/身份证号
- 检查地址、电话等联系方式是否完整
- 确认法定代表人/负责人信息是否完整
2. 主体信息正确性：
- 核对企业名称是否与营业执照一致，不使用简称
- 检查统一社会信用代码/身份证号格式是否正确
- 确认主体信息与公开渠道可查询的信息是否一致
3. 特殊主体审查：
- 自然人身份审查：确认身份证信息、民事行为能力、精神状态
- 公司身份审查：经营范围、经营状态、证照有效性、特殊行业资质
- 分公司审查：是否依法设立登记、与母公司关系、责任承担机制
- 外国企业审查：依法设立、法律形式、责任承担方式
- 代理人审查：授权委托书、权限范围、授权期限

## 三、业务条款审查
1. 合同目的与期限条款：
- 合同目的是否清晰表达
- 合同背景与基本情况是否概述
- 合同起始与终止时间是否明确
- 续约条款（如有）是否明确规定续约条件与程序
2. 合同标的条款：
- 标的物数量是否具体明确，使用明确单位
- 标的物类别、品牌、型号、规格是否清晰描述
- 标的物质量标准是否明确（行业标准、国家标准或约定标准）
- 验收条款是否具有操作性（时间、方式、标准、不合格处理流程）
- 标的物的合法性与权属状况是否说明清楚（是否存在抵押、查封等）
3. 合同价款条款：
- 价格构成是否明确（单价、总价、计算方式）
- 计价方式是否明确（按件、按时间、按工作量等）
- 货币单位是否明确，汇率问题是否考虑（跨境交易）
- 价税是否分离，税费承担是否明确
- 付款方式是否明确（一次性、分期、质保金）
- 付款节点是否与履行进度匹配
- 付款条件是否明确且可操作
- 付款凭证与发票约定是否清晰
4. 合同履行条款：
- 履行时间是否明确具体（避免"合理时间"等模糊表述）
- 履行地点是否具体明确
- 履行方式是否详细描述（交付方式、包装要求、运输方式）
- 履行程序是否结构化说明（每个步骤的具体操作）
- 权利转移点是否明确（所有权转移时间）
- 风险转移点是否明确（风险责任承担时间）
- 履行中的通知义务是否明确规定
5. 权利义务条款：
- 主要权利是否全面列举，无遗漏
- 是否存在隐含的弃权条款
- 豁免条款是否合理（特别是不可抗力范围）
- 主要义务是否无遗漏，履行标准是否明确
- 义务的合理性与可执行性
- 后合同义务是否明确（如保密延续期限）
- 从权利义务是否明确（附属于主权利的权利义务）
6. 知识产权条款：
- 现有知识产权归属是否明确
- 合同履行过程中产生的知识产权归属是否明确
- 知识产权使用权范围、目的、期限是否明确
- 知识产权转让与许可条件是否清晰
- 知识产权保护与维护责任如何分配
- 保密与竞争限制期限、范围是否合理

## 四、法律条款审查
1. 生效条款：
- 合同成立与生效是否有明确区分
- 生效条件是否明确（签署即生效、附条件生效、附期限生效）
- 生效条件的可行性是否考虑
- 生效前的法律责任如何安排
2. 违约责任条款：
- 违约行为的定义是否明确全面（迟延履行、质量不合格、拒绝履行等）
- 违约责任形式是否明确（继续履行、采取补救、赔偿损失、支付违约金）
- 违约金比例是否合理（既不过高具惩罚性，也不过低难以弥补损失）
- 违约责任是否对双方公平（注意违约金比例是否对等）
- 违约责任的计算方式是否明确
3. 合同变更、解除、终止条款：
- 变更条件是否明确（哪些情况下可以变更）
- 变更程序是否规范（书面变更、通知方式、签署程序）
- 解除条件是否合理（法定解除条件、约定解除条件）
- 解除程序的操作性（通知方式、时间限制）
- 终止条件的明确性（何种情况下自动终止）
- 存续条款的合理性（哪些条款在合同终止后继续有效）
- 终止后的权利义务安排（清算、资料返还等）
4. 法律适用条款：
- 适用法律是否明确（具体到哪个国家/地区的法律）
- 所选法律的合理性（与合同标的、履行地的关联）
- 是否与强制性规定冲突（履行地法律的强制性规定）
- 选择的法律在实际纠纷中的可适用性与可执行性
5. 保密条款：
- 保密信息范围是否明确定义
- 保密期限是否明确且合理
- 例外情况是否合理且有限定
- 违反保密义务的责任是否明确
6. 不可抗力条款：
- 不可抗力事件定义是否合理（避免将可控因素纳入）
- 通知义务是否明确（时间、方式、证明材料）
- 责任减免条件是否公平合理
- 不可抗力事件持续的后续处理措施是否明确
7. 争议解决条款：
- 争议解决方式选择是否明确（协商、诉讼、仲裁）
- 管辖地点或仲裁机构是否明确
- 是否存在争议解决方式冲突（同时约定仲裁和诉讼）
- 适用法律选择是否与争议解决方式匹配
8. 送达条款：
- 送达方式是否明确（当面送达、邮寄、电子邮件等）
- 送达地址或联系方式是否准确完整
- 送达时间和生效条件是否明确
- 地址变更通知义务是否明确
9. 授权条款：
- 授权人员身份是否明确具体
- 授权范围和权限是否清晰界定
- 授权期限是否合理规定
- 撤销或变更授权的机制是否完善
10. 其他法律条款：
- 解释规则是否明确（条款冲突处理原则）
- 签订时间和地点是否明确
- 条款的独立性是否明确（部分无效不影响整体）
"""

_PARTY_LABELS: dict[str, str] = {
    "party_a": "甲方",
    "party_b": "乙方",
    "party_c": "丙方",
    "party_d": "丁方",
}


@dataclass
class ReviewResult:
    original: str
    suggested: str
    reason: str
    paragraph_index: int


class ContractReviewer:
    """基于用户代表方立场审查合同条款"""

    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    def review_contract(
        self,
        paragraphs: list[str],
        represented_party: str,
        party_a: str,
        party_b: str,
        model_name: str = "",
    ) -> list[ReviewResult]:
        """将合同全文和代表方信息发送给 LLM，返回修改建议"""
        text = "\n".join(f"[段落{i}] {p}" for i, p in enumerate(paragraphs))
        prompt = self._build_revision_prompt(text, represented_party, party_a, party_b)
        try:
            resp = self._llm.complete(
                prompt=prompt,
                model=model_name or None,
                temperature=0.3,
                max_tokens=32768,
                fallback=False,
            )
            return self._parse_revision_response(resp.content)
        except Exception:
            logger.exception("合同审查 LLM 调用失败")
            return []

    def generate_report(
        self,
        paragraphs: list[str],
        represented_party: str,
        party_a: str,
        party_b: str,
        model_name: str = "",
    ) -> str:
        """生成合同评估报告（Markdown 格式）"""
        text = "\n".join(f"[段落{i}] {p}" for i, p in enumerate(paragraphs))
        prompt = self._build_report_prompt(text, represented_party, party_a, party_b)
        try:
            resp = self._llm.complete(
                prompt=prompt,
                model=model_name or None,
                temperature=0.3,
                max_tokens=32768,
                fallback=False,
            )
            return resp.content.strip()
        except Exception:
            logger.exception("评估报告生成失败")
            return ""

    @staticmethod
    def _build_revision_prompt(text: str, represented_party: str, party_a: str, party_b: str) -> str:
        party_label = _PARTY_LABELS.get(represented_party, "甲方")
        party_name = party_a if represented_party == "party_a" else party_b
        return (
            f"请作为一名具有多年经验的合同法律顾问，代表{party_label}（{party_name}）的利益，"
            "对以下合同进行全面审查，找出需要修改的条款，输出精确的修改建议。\n"
            f"甲方：{party_a}，乙方：{party_b}\n\n"
            f"{_REVIEW_FRAMEWORK}\n"
            "## 输出要求\n"
            "- 不要修改错别字或语法问题（已有专门检查）\n"
            "- original 必须是合同中的**原文片段**（精确逐字匹配，不要省略或改动任何字符）\n"
            "- original 尽量短，只包含需要修改的关键句子或短语\n"
            "- suggested 是修改后的完整替换文本\n"
            "- reason 简要说明修改理由和风险等级（高/中/低）\n"
            "每个段落前标注了段落编号 [段落N]。\n"
            "仅返回 JSON 数组，格式：\n"
            '[{"original": "原文片段", "suggested": "修改后文本", '
            '"reason": "【高/中/低】修改理由", "paragraph_index": 段落编号}]\n'
            "如果没有需要修改的条款，返回空数组 []。\n"
            "不要返回任何其他内容。\n\n"
            f"{text}"
        )

    @staticmethod
    def _build_report_prompt(text: str, represented_party: str, party_a: str, party_b: str) -> str:
        party_label = _PARTY_LABELS.get(represented_party, "甲方")
        party_name = party_a if represented_party == "party_a" else party_b
        return (
            f"请作为一名具有多年经验的合同法律顾问，代表{party_label}（{party_name}）的利益，"
            "对以下合同进行全面、细致的审查，严格按照企业合同风险管控标准识别所有潜在问题与风险。"
            "请遵循以下详细审核框架，不要遗漏任何一个审查点：\n"
            f"甲方：{party_a}，乙方：{party_b}\n\n"
            f"{_REVIEW_FRAMEWORK}\n"
            "请逐条分析此合同中存在的每一个问题，对每个问题说明：\n"
            "1. 问题的具体位置和内容\n"
            "2. 为什么这构成风险或问题\n"
            "3. 风险等级（高/中/低）\n"
            "4. 修改建议\n\n"
            "最后，请提供一个总体评估，指出最严重的三个问题和最需要优先修改的内容。\n\n"
            "合同全文如下：\n\n"
            f"{text}"
        )

    @staticmethod
    def _parse_revision_response(response_text: str) -> list[ReviewResult]:
        text = response_text.strip()
        if "```" in text:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                text = text[start:end]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # 尝试修复被截断的 JSON：找到最后一个完整的 },] 截断
            data = _try_fix_truncated_json(text)
            if data is None:
                logger.warning("合同审查 JSON 解析失败: %s", text[:200])
                return []

        if not isinstance(data, list):
            return []

        results: list[ReviewResult] = []
        for item in data:
            if isinstance(item, dict) and "original" in item and "suggested" in item:
                results.append(
                    ReviewResult(
                        original=str(item["original"]),
                        suggested=str(item["suggested"]),
                        reason=str(item.get("reason", "")),
                        paragraph_index=_parse_int(item.get("paragraph_index", 0)),
                    )
                )
        return results


def _parse_int(val: object) -> int:
    if isinstance(val, int):
        return val
    s = str(val).strip()
    m = re.search(r"\d+", s)
    return int(m.group()) if m else 0


def _try_fix_truncated_json(text: str) -> list[dict[str, object]] | None:
    """尝试修复被截断的 JSON 数组，返回已解析的完整条目"""
    # 找到最后一个 "}," 或 "}" 截断点
    last_brace = text.rfind("}")
    if last_brace < 0:
        return None
    # 尝试在最后一个 } 后加 ]
    candidate = text[: last_brace + 1].rstrip().rstrip(",") + "]"
    try:
        data = json.loads(candidate)
        if isinstance(data, list):
            logger.info("修复截断 JSON 成功，恢复 %d 条", len(data))
            return data
    except json.JSONDecodeError:
        pass
    return None
