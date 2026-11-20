"""``question_request.questions`` 的字段名必须与 ``normalize_questions`` 的产物同源。

历史问题：该字段原先声明成 ``list[dict[str, Any]]``，生成出来的 TS 只有
``Record<string, unknown>[]``——前端要渲染「向律师提问」的卡片，只能去读
``services/question.py`` 猜字段名，而「查 OpenAPI 才能写前端」是本仓库的红线。

改成 ``QuestionSpec`` 之后，字段名进 TS / OpenAPI；本文件守的是**另一半**：
声明与归一化实现不能各写一套。漂移的表现是前端某个字段永远 ``undefined``
（卡片少一行选项、或「允许自由输入」永远为假），而端到端不会报任何错。

注意这里**不加运行时校验**：``QuestionSpec`` 是线路契约声明，真正的宽容解析在
``normalize_questions``（模型常把 options 写成字符串数组等）。所以断言的是
「字段名集合相等」与「归一化产物能被契约模型接受」，不是「非法输入会被拒」。
"""

from __future__ import annotations

from apps.agent.services.question import normalize_questions
from apps.agent.sse_types import QuestionOption, QuestionRequestEvent, QuestionSpec, generate_ts

#: 一份**把所有字段都写出来**的模型输入（归一化后每个 key 都会出现）。
_RAW_QUESTIONS = [
    {
        "id": "jurisdiction",
        "question": "管辖地选哪个？",
        "context": "合同未约定管辖",
        "options": [
            "北京",
            {"label": "上海", "description": "被告所在地"},
        ],
        "allow_freeform": False,
        "allow_multiple": True,
        "allow_comment": True,
    }
]


def test_question_fields_match_normalizer_output() -> None:
    """``QuestionSpec`` 的字段集合 == ``normalize_questions`` 产物的键集合。"""
    normalized = normalize_questions(_RAW_QUESTIONS)

    assert set(QuestionSpec.model_fields) == set(normalized[0]), (
        "契约字段与归一化产物的键不一致：改 normalize_questions 的键必须同步改 "
        "sse_types.QuestionSpec（前端照 TS 读字段）。"
    )


def test_option_fields_match_normalizer_output() -> None:
    """选项的字段名同理（``label`` / ``description``）。"""
    normalized = normalize_questions(_RAW_QUESTIONS)
    option = normalized[0]["options"][1]

    assert set(QuestionOption.model_fields) == set(option)
    # 字符串选项也要归一成对象（前端只认一种形状）
    assert set(normalized[0]["options"][0]) == set(QuestionOption.model_fields)


def test_normalized_payload_is_accepted_by_the_contract() -> None:
    """归一化产物能被契约模型直接接受（类型漂移会在这里红）。

    只比字段名不够：把 ``allow_multiple`` 改成 ``int``、或把 ``options`` 改成
    ``dict``，字段名集合仍然相等，但前端拿到的形状已经变了。``model_validate``
    走的是与生成 TS 同一份 ``model_fields``，所以这条能挡住类型层面的漂移。
    """
    normalized = normalize_questions(_RAW_QUESTIONS)

    event = QuestionRequestEvent.model_validate(
        {"type": "question_request", "question_id": "q-1", "questions": normalized, "timeout_seconds": 180}
    )

    assert event.questions[0].id == "jurisdiction"
    assert event.questions[0].options[1].label == "上海"
    assert event.questions[0].options[1].description == "被告所在地"
    assert event.questions[0].allow_freeform is False
    assert event.questions[0].allow_multiple is True


def test_generated_ts_exposes_question_field_names() -> None:
    """生成物里必须出现 questions 的字段名（否则前端还是只能猜）。"""
    ts = generate_ts()

    for name in QuestionSpec.model_fields:
        assert f"{name}" in ts, f"生成物缺少 QuestionSpec.{name}"
    for name in QuestionOption.model_fields:
        assert f"{name}" in ts, f"生成物缺少 QuestionOption.{name}"
    # 不能退化回 Record<string, unknown>（那就是本次要修的形状）
    assert "questions?: Record<string, unknown>[]" not in ts
