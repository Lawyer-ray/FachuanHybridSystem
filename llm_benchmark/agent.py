"""
双进程对话 agent
用法:
  进程1（律师）: python agent.py --role lawyer --inbox msg_b.txt --outbox msg_a.txt --first
  进程2（程序员）: python agent.py --role programmer --inbox msg_a.txt --outbox msg_b.txt
"""

import argparse
import asyncio
import logging
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "http://116.196.92.174:8001/v1/chat/completions"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer sk-abc123xyz789",
}
MODEL = "Qwen3.5-397B-A17B"

SYSTEM_PROMPTS = {
    "lawyer": (
        "你是中国最顶尖的诉讼律师，有30年一线庭审经验，代理过无数重大商事、刑事案件。"
        "你深刻理解司法实践的痛点：证据整理耗时、庭审准备繁琐、法条检索低效、当事人沟通成本高。"
        "你正在和一位顶尖程序员探讨法律科技的落地方向。"
        "每次回复300字以内，直接表达观点，用中文回答，不要输出思考过程。"
        "要具体、务实，结合真实诉讼场景提出需求和痛点，推动对话深入。"
    ),
    "programmer": (
        "你是硅谷顶尖全栈程序员，精通AI/ML、大语言模型、RAG、知识图谱、OCR、自动化工作流等技术。"
        "你正在和一位顶尖诉讼律师探讨法律科技的落地方向。"
        "每次回复300字以内，直接表达观点，用中文回答，不要输出思考过程。"
        "要具体说明技术实现路径、难点和可行性，针对律师的痛点给出可落地的方案，推动对话深入。"
    ),
}

ROLE_LABELS = {
    "lawyer": "⚖️  律师",
    "programmer": "💻 程序员",
}

FIRST_MESSAGE = (
    "我们来聊聊法律科技。作为一线律师，我每天最大的痛苦是证据整理——"
    "一个案子动辄几百份文件，光是归类、提取关键信息就要耗费大量时间。"
    "你觉得技术上能怎么解决这个问题？有没有真正能落地的方案？"
)


def wait_for_file(path: Path, timeout: int = 300) -> str:
    """等待文件出现并读取内容，读完后删除"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists() and path.stat().st_size > 0:
            content = path.read_text(encoding="utf-8").strip()
            path.unlink()
            return content
        time.sleep(0.5)
    raise TimeoutError(f"等待 {path} 超时")


def write_message(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


async def run(role: str, inbox: Path, outbox: Path, first: bool, rounds: int) -> None:
    system_prompt = SYSTEM_PROMPTS[role]
    label = ROLE_LABELS[role]
    history: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    async with httpx.AsyncClient(headers=HEADERS, timeout=180) as client:
        for i in range(rounds):
            # 获取对方消息
            if first and i == 0:
                incoming = FIRST_MESSAGE
                logger.info(f"\n{'='*60}\n[开场白]:\n{incoming}\n")
            else:
                logger.info(f"⏳ 等待对方回复...")
                incoming = wait_for_file(inbox)

            history.append({"role": "user", "content": incoming})

            # 调用模型
            payload = {
                "model": MODEL,
                "messages": history,
                "max_tokens": 2048,
                "temperature": 0.8,
            }
            t0 = time.perf_counter()
            resp = await client.post(BASE_URL, json=payload)
            elapsed = (time.perf_counter() - t0) * 1000

            if resp.status_code != 200:
                logger.error(f"请求失败: {resp.status_code} {resp.text[:200]}")
                break

            raw = resp.json()["choices"][0]["message"]["content"]
            reply = strip_thinking(raw)
            history.append({"role": "assistant", "content": reply})

            logger.info(f"\n{'='*60}")
            logger.info(f"{label} (轮{i+1}) [{elapsed:.0f}ms]:")
            logger.info(reply)

            # 写出消息给对方
            write_message(outbox, reply)


def strip_thinking(text: str) -> str:
    import re
    # </think> 标签后的内容
    m = re.search(r"</think>\s*(.*)", text, re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip()
    # *Draft N:* 后的中文内容
    drafts = re.findall(
        r"\*Draft \d+:\*\s*([\u4e00-\u9fff].*?)(?=\*(?:Count|Check|Refin)|$)",
        text, re.DOTALL
    )
    if drafts:
        return drafts[-1].strip()
    # 最后一段中文段落
    paras = re.split(r"\n{2,}", text)
    chinese = [
        p.strip() for p in paras
        if len(re.findall(r"[\u4e00-\u9fff]", p)) > 10
        and not re.search(r"\*\*Anal|\*\*Role|\*\*Draft|\*\*Count|\*\*Check", p)
    ]
    if chinese:
        return chinese[-1]
    return text.strip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["lawyer", "programmer"], required=True)
    parser.add_argument("--inbox", type=Path, required=True, help="读取对方消息的文件")
    parser.add_argument("--outbox", type=Path, required=True, help="写出自己消息的文件")
    parser.add_argument("--first", action="store_true", help="是否先发第一条消息")
    parser.add_argument("--rounds", type=int, default=10000)
    args = parser.parse_args()

    # 清理残留文件
    for f in [args.inbox, args.outbox]:
        if f.exists():
            f.unlink()

    try:
        asyncio.run(run(args.role, args.inbox, args.outbox, args.first, args.rounds))
    except KeyboardInterrupt:
        logger.info("\n👋 已停止")
