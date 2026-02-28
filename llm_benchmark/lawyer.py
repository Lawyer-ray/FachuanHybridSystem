"""律师 Agent - 通过 SQLite 与程序员对话"""

import asyncio
import logging
import sqlite3
import time
import re
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [律师] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "conversation.db"
BASE_URL = "http://116.196.92.174:8001/v1/chat/completions"
HEADERS = {"Content-Type": "application/json", "Authorization": "Bearer sk-abc123xyz789"}
MODEL = "Qwen3.5-397B-A17B"

SYSTEM_PROMPT = (
    "你是中国最顶尖的诉讼律师，有30年一线庭审经验，代理过无数重大商事、刑事案件。"
    "你深刻理解司法实践的痛点：证据整理耗时、庭审准备繁琐、法条检索低效、当事人沟通成本高。"
    "你正在和一位顶尖程序员探讨法律科技的落地方向。"
    "每次回复300字以内，直接表达观点，用中文回答，不要输出思考过程。"
    "要具体、务实，结合真实诉讼场景提出需求和痛点，推动对话深入探讨具体落地方案。"
    "每轮对话要基于对方的回复继续深入，不要重复之前说过的内容。"
)

FIRST_MESSAGE = (
    "我们来聊聊法律科技。作为一线律师，我每天最大的痛苦是证据整理——"
    "一个案子动辄几百份文件，光是归类、提取关键信息就要耗费大量时间。"
    "你觉得技术上能怎么解决这个问题？有没有真正能落地的方案？"
)
