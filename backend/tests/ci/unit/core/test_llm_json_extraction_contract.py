"""权威 LLM JSON 解析实现的输入/输出契约。

本文件把 ``apps/core/llm/structured_output.py`` 里的 ``extract_json_text`` /
``parse_json_content`` 在当前 21 类代表性输入上的行为**固化**下来。

存在的意义：仓库里还有几份自签的 JSON 解析实现（相似度评分、身份证识别、
记忆抽取、材料分类）**有意**没有合并到权威实现，原因是它们与权威实现在
若干输入上分叉，而分叉会静默改变业务语义。改权威实现之前，先看这里哪些
case 会动——它们既是上游回归护栏，也是「不能随手统一」的证据。

分叉 case 逐条注释了影响面，标注为「有意保留的差异，不是 bug」。
"""

from __future__ import annotations

import json

import pytest

from apps.core.llm.structured_output import extract_json_text, parse_json_content

PLAIN_OBJECT = '{"type":"summons","confidence":0.9}'
FENCED_JSON = '```json\n{"type":"summons"}\n```'
FENCED_PLAIN = '```\n{"type":"summons"}\n```'
TEXT_AROUND = 'Here is result: {"a":1} done'
NESTED_WITH_TEXT = 'text {"a":{"b":1}} tail'
TWO_OBJECTS = 'x {"a":1} y {"a":2}'
TOP_LEVEL_ARRAY = '[{"a":1},{"b":2}]'
ARRAY_WITH_TEXT = 'x [{"a":1}] y'
EMPTY_STRING = ""
NO_JSON = "no json at all"
TRUNCATED = '{"a":1'
FENCE_NON_JSON = "```json\nnot json\n```"
FENCE_AFTER_PREFIX = 'ok:\n```json\n{"a":1}\n```'
OBJECT_THEN_ARRAY = 'see {"a":1} and [1,2,3]'
OBJECT_THEN_BRACES_PROSE = '{"a":1} note: use { } braces'
BRACES_PROSE_THEN_OBJECT = 'note: use { } braces {"a":1}'
NESTED_ARRAY_IN_OBJECT = '{"a":[{"b":1}]}'
BRACE_IN_STRING = '{"a":"}"}'
MULTILINE_WITH_PROSE = "说明：\n{\"a\": 1}\n以上。"
BAD_OBJECT_THEN_GOOD = '{"bad": } and {"a":1}'
UPPERCASE_FENCE = '```JSON\n{"a":1}\n```'
OBJECT_AFTER_HEADING = "## Result\n{\"a\":1}\n## End"

# 权威实现在这些输入上的当前结果（对象/数组/dict 形式）。
EXPECTED_EXTRACTIONS: list[tuple[str, str, object]] = [
    ("纯 JSON 对象", PLAIN_OBJECT, {"type": "summons", "confidence": 0.9}),
    ("json 围栏", FENCED_JSON, {"type": "summons"}),
    ("裸围栏", FENCED_PLAIN, {"type": "summons"}),
    ("前后说明文字", TEXT_AROUND, {"a": 1}),
    ("嵌套对象+前后文字", NESTED_WITH_TEXT, {"a": {"b": 1}}),
    # 有意保留的差异，不是 bug：权威实现取第一个完整对象，
    # 相似度评分与身份识别的自签实现会返回 None，并因此走不同的降级路径。
    ("两个对象无说明", TWO_OBJECTS, {"a": 1}),
    ("顶层数组", TOP_LEVEL_ARRAY, [{"a": 1}, {"b": 2}]),
    # 有意保留的差异，不是 bug：权威实现优先返回数组，
    # 自签实现（正则 \{.*\}）会返回数组里的对象。
    ("顶层数组+前后文字", ARRAY_WITH_TEXT, [{"a": 1}]),
    ("围栏在带前缀文本中", FENCE_AFTER_PREFIX, {"a": 1}),
    ("对象后跟数组描述", OBJECT_THEN_ARRAY, {"a": 1}),
    ("JSON 后跟散文中的空大括号", OBJECT_THEN_BRACES_PROSE, {"a": 1}),
    # 有意保留的差异，不是 bug：原文里最先出现的 `{ }` 会被当成合法 JSON 对象，
    # 权威实现返回空 dict `{}`，而后面的真实对象被丢掉。相似度评分若替换成
    # 权威实现，`coerce_score(payload.get("score", 0.0))` 会直接判 0 分并绕过
    # `_repair_json_payload` 修复路径——这是静默的错误评分。
    ("散文中的空大括号先于真实对象", BRACES_PROSE_THEN_OBJECT, {}),
    ("嵌套数组于对象", NESTED_ARRAY_IN_OBJECT, {"a": [{"b": 1}]}),
    ("字符串内含大括号", BRACE_IN_STRING, {"a": "}"}),
    ("多行含说明文字", MULTILINE_WITH_PROSE, {"a": 1}),
    ("坏对象后跟好对象", BAD_OBJECT_THEN_GOOD, {"a": 1}),
    ("大写 JSON 围栏标签", UPPERCASE_FENCE, {"a": 1}),
    ("markdown 标题后的对象", OBJECT_AFTER_HEADING, {"a": 1}),
]

EXPECTED_NONE: list[tuple[str, str]] = [
    ("空字符串", EMPTY_STRING),
    ("无 JSON", NO_JSON),
    ("截断 JSON", TRUNCATED),
    ("围栏内含非 JSON", FENCE_NON_JSON),
]


@pytest.mark.parametrize(("label", "text", "expected"), EXPECTED_EXTRACTIONS, ids=[c[0] for c in EXPECTED_EXTRACTIONS])
def test_extract_json_text_matches_contract(label: str, text: str, expected: object) -> None:
    snippet = extract_json_text(text)
    assert snippet is not None, f"{label}: 期望能提取出 JSON"
    assert json.loads(snippet) == expected, f"{label}: 提取结果与契约不符"


@pytest.mark.parametrize(("label", "text"), EXPECTED_NONE, ids=[c[0] for c in EXPECTED_NONE])
def test_extract_json_text_returns_none_for_unparseable(label: str, text: str) -> None:
    assert extract_json_text(text) is None, f"{label}: 期望返回 None"


@pytest.mark.parametrize(("label", "text", "expected"), EXPECTED_EXTRACTIONS, ids=[c[0] for c in EXPECTED_EXTRACTIONS])
def test_parse_json_content_roundtrip(label: str, text: str, expected: object) -> None:
    assert parse_json_content(text) == expected, f"{label}: parse_json_content 与契约不符"


@pytest.mark.parametrize(("label", "text"), EXPECTED_NONE, ids=[c[0] for c in EXPECTED_NONE])
def test_parse_json_content_raises_for_unparseable(label: str, text: str) -> None:
    with pytest.raises(ValueError, match="does not contain valid JSON"):
        parse_json_content(text)
