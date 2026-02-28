"""程序员 Agent - 通过 Redis 与律师对话"""

import asyncio
import logging
import time
import re
import redis
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [程序员] %(message)s")
logger = logging.getLogger(__name__)

# Redis 配置
REDIS_HOST = "localhost"
REDIS_PORT = 6379
CHANNEL_LAWYER = "lawyer_says"      # 律师发言频道
CHANNEL_PROGRAMMER = "programmer_says"  # 程序员发言频道

# LLM 配置
BASE_URL = "http://116.196.92.174:8001/v1/chat/completions"
HEADERS = {"Content-Type": "application/json", "Authorization": "Bearer sk-abc123xyz789"}
MODEL = "Qwen3.5-397B-A17B"

SYSTEM_PROMPT = (
    "你是硅谷顶尖全栈程序员，精通AI/ML、大语言模型、RAG、知识图谱、OCR、自动化工作流等技术。"
    "你正在和一位顶尖诉讼律师探讨法律科技的落地方向。"
    "每次回复300字以内，直接表达观点，用中文回答，不要输出思考过程。"
    "要具体说明技术实现路径、难点和可行性，针对律师的痛点给出可落地的方案，推动对话深入。"
)


def strip_thinking(text: str) -> str:
    m = re.search(r"</think>\s*(.*)", text, re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip()
    drafts = re.findall(r"\*Draft \d+:\*\s*([\u4e00-\u9fff].*?)(?=\*(?:Count|Check|Refin)|$)", text, re.DOTALL)
    if drafts:
        return drafts[-1].strip()
    paras = re.split(r"\n{2,}", text)
    chinese = [p.strip() for p in paras if len(re.findall(r"[\u4e00-\u9fff]", p)) > 10]
    return chinese[-1] if chinese else text.strip()


async def call_llm(client: httpx.AsyncClient, history: list[dict]) -> str:
    payload = {"model": MODEL, "messages": history, "max_tokens": 2048, "temperature": 0.8}
    t0 = time.perf_counter()
    resp = await client.post(BASE_URL, json=payload, timeout=180)
    elapsed = (time.perf_counter() - t0) * 1000
    if resp.status_code != 200:
        raise Exception(f"LLM 请求失败: {resp.status_code}")
    raw = resp.json()["choices"][0]["message"]["content"]
    clean = strip_thinking(raw)
    logger.info(f"[{elapsed:.0f}ms] 回复:\n{clean}\n")
    return clean


async def main() -> None:
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    pubsub = r.pubsub()
    pubsub.subscribe(CHANNEL_LAWYER)
    
    history: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    round_num = 0
    
    async with httpx.AsyncClient(headers=HEADERS) as client:
        logger.info("⏳ 等待律师发言...")
        
        for msg in pubsub.listen():
            if msg["type"] == "message":
                incoming = msg["data"]
                round_num += 1
                logger.info(f"\n{'='*60}\n[轮{round_num}] 收到律师:\n{incoming}\n")
                
                history.append({"role": "user", "content": incoming})
                reply = await call_llm(client, history)
                history.append({"role": "assistant", "content": reply})
                r.publish(CHANNEL_PROGRAMMER, reply)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 已停止")
