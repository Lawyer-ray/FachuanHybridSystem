"""内容运营模块常量配置。"""

from __future__ import annotations

# LLM 模型名称
CONTENT_LLM_MODEL = "mimo-v2.5-pro"

# TTS 模型名称
TTS_MODEL = "mimo-v2.5-tts"
TTS_MODEL_VOICEDESIGN = "mimo-v2.5-tts-voicedesign"

# 多人讨论默认角色
DEFAULT_DISCUSSION_SPEAKERS: list[dict[str, str]] = [
    {
        "name": "主持人",
        "role": "播客主持人，负责引导话题、提问、总结",
        "style_prompt": "一个热情的播客主持人，声音清晰有力，语速适中，善于引导话题和提问",
    },
    {
        "name": "张律师",
        "role": "资深律师，负责法律分析和专业解读",
        "style_prompt": "一个中年男性律师，声音沉稳专业，说话条理清晰，善于用通俗语言解释法律概念",
    },
    {
        "name": "李大姐",
        "role": "社区热心人，代表普通群众的视角，负责提出接地气的问题",
        "style_prompt": "一个中年女性邻居，说话亲切自然，语速稍慢，带有生活气息和好奇心",
    },
]
