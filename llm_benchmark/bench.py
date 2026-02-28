"""
LLM 压力测试工具
测试目标：上下文长度极限、响应速度、并发能力、双进程对话
"""

import asyncio
import time
import json
import logging
import argparse
from dataclasses import dataclass, field
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "http://116.196.92.174:8001/v1/chat/completions"
API_KEY = "sk-abc123xyz789"
MODEL = "Qwen3.5-397B-A17B"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}


@dataclass
class BenchResult:
    test_name: str
    success: bool
    input_tokens: int = 0
    output_tokens: int = 0
    first_token_ms: float = 0.0
    total_ms: float = 0.0
    tokens_per_sec: float = 0.0
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def build_payload(
    messages: list[dict[str, str]],
    max_tokens: int = 256,
    stream: bool = False,
    temperature: float = 0.7,
    thinking: bool = False,
) -> dict[str, Any]:
    return {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream,
        "temperature": temperature,
        "enable_thinking": thinking,
    }

def strip_thinking(text: str) -> str:
    """提取 Qwen3.5 thinking 后的实际回答"""
    import re
    # 方式1: <think>...</think> 标签（标准格式）
    m = re.search(r"</think>\s*(.*)", text, re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip()
    # 方式2: Qwen3.5 非标准格式 — 找最后一个 *Draft N:* 之后的中文内容
    drafts = re.findall(r"\*Draft \d+:\*\s*([\u4e00-\u9fff].*?)(?=\*(?:Count|Check|Refin)|$)", text, re.DOTALL)
    if drafts:
        return drafts[-1].strip()
    # 方式3: 找最后一段纯中文段落（10字以上，不含英文分析标记）
    paras = re.split(r"\n{2,}", text)
    chinese_paras = [
        p.strip() for p in paras
        if len(re.findall(r"[\u4e00-\u9fff]", p)) > 10
        and not re.search(r"\*\*|^\d+\.\s+\*\*", p)
    ]
    if chinese_paras:
        return chinese_paras[-1]
    return text.strip()


# ─── 1. 上下文长度探测 ───────────────────────────────────────────

async def test_context_length(client: httpx.AsyncClient) -> list[BenchResult]:
    """二分法探测最大上下文长度"""
    results: list[BenchResult] = []
    # 每个中文字约 1-2 token，用重复文本填充
    filler = "这是一段用于测试上下文长度极限的填充文本。" * 100  # ~2000字

    async def try_length(char_count: int) -> bool:
        text = filler * (char_count // len(filler) + 1)
        text = text[:char_count]
        messages = [
            {"role": "user", "content": f"{text}\n\n请用一个字回答：你好吗？"}
        ]
        payload = build_payload(messages, max_tokens=16)
        try:
            t0 = time.perf_counter()
            resp = await client.post(BASE_URL, json=payload, timeout=120)
            elapsed = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                usage = data.get("usage", {})
                results.append(BenchResult(
                    test_name=f"context_{char_count}chars",
                    success=True,
                    input_tokens=usage.get("prompt_tokens", 0),
                    total_ms=elapsed,
                    extra={"char_count": char_count},
                ))
                logger.info(f"✅ {char_count} 字符通过 | prompt_tokens={usage.get('prompt_tokens', '?')} | {elapsed:.0f}ms")
                return True
            else:
                logger.warning(f"❌ {char_count} 字符失败 | status={resp.status_code} | {resp.text[:200]}")
                results.append(BenchResult(
                    test_name=f"context_{char_count}chars",
                    success=False,
                    error=resp.text[:200],
                    extra={"char_count": char_count},
                ))
                return False
        except Exception as e:
            logger.warning(f"❌ {char_count} 字符异常 | {e}")
            results.append(BenchResult(
                test_name=f"context_{char_count}chars", success=False, error=str(e),
                extra={"char_count": char_count},
            ))
            return False

    # 先用指数增长找到上界
    length = 2000
    max_ok = 0
    while length <= 512_000:
        ok = await try_length(length)
        if ok:
            max_ok = length
            length *= 2
        else:
            break

    # 二分精确定位
    if max_ok > 0 and max_ok < length:
        lo, hi = max_ok, length
        while hi - lo > 5000:
            mid = (lo + hi) // 2
            if await try_length(mid):
                lo = mid
            else:
                hi = mid
        logger.info(f"📏 上下文极限约 {lo} 字符 (~{results[-1].input_tokens if results else '?'} tokens)")

    return results


# ─── 2. 响应速度测试（流式） ─────────────────────────────────────

async def test_speed(client: httpx.AsyncClient) -> list[BenchResult]:
    """测试首 token 延迟和生成吞吐量"""
    results: list[BenchResult] = []
    prompts = [
        ("short", "你好", 64),
        ("medium", "请详细解释量子计算的基本原理，包括量子比特、叠加态和量子纠缠。", 512),
        ("long", "请写一篇关于人工智能发展历史的详细文章，从图灵测试到现代大语言模型。", 1024),
    ]

    for label, prompt, max_tokens in prompts:
        messages = [{"role": "user", "content": prompt}]
        payload = build_payload(messages, max_tokens=max_tokens, stream=True)

        t0 = time.perf_counter()
        first_token_time: float | None = None
        token_count = 0
        full_text = ""

        try:
            async with client.stream("POST", BASE_URL, json=payload, timeout=180) as resp:
                if resp.status_code != 200:
                    results.append(BenchResult(
                        test_name=f"speed_{label}", success=False,
                        error=f"status={resp.status_code}",
                    ))
                    continue

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            if first_token_time is None:
                                first_token_time = time.perf_counter()
                            token_count += 1
                            full_text += content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

            total_ms = (time.perf_counter() - t0) * 1000
            ftl = ((first_token_time - t0) * 1000) if first_token_time else 0
            tps = (token_count / (total_ms / 1000)) if total_ms > 0 else 0

            result = BenchResult(
                test_name=f"speed_{label}",
                success=True,
                output_tokens=token_count,
                first_token_ms=ftl,
                total_ms=total_ms,
                tokens_per_sec=tps,
            )
            results.append(result)
            logger.info(
                f"⚡ {label}: 首token={ftl:.0f}ms | "
                f"总耗时={total_ms:.0f}ms | "
                f"输出={token_count}tokens | "
                f"速度={tps:.1f} tok/s"
            )
        except Exception as e:
            results.append(BenchResult(
                test_name=f"speed_{label}", success=False, error=str(e),
            ))
            logger.error(f"speed_{label} 异常: {e}")

    return results


# ─── 3. 并发压力测试 ─────────────────────────────────────────────

async def test_concurrency(client: httpx.AsyncClient, levels: list[int] | None = None) -> list[BenchResult]:
    """不同并发数下的吞吐量"""
    if levels is None:
        levels = [1, 2, 4, 8, 16]
    results: list[BenchResult] = []

    async def single_request() -> tuple[bool, float]:
        payload = build_payload(
            [{"role": "user", "content": "用一句话介绍Python。"}],
            max_tokens=64,
        )
        t0 = time.perf_counter()
        try:
            resp = await client.post(BASE_URL, json=payload, timeout=60)
            elapsed = (time.perf_counter() - t0) * 1000
            return resp.status_code == 200, elapsed
        except Exception:
            elapsed = (time.perf_counter() - t0) * 1000
            return False, elapsed

    for n in levels:
        logger.info(f"🔥 并发测试: {n} 个请求...")
        t0 = time.perf_counter()
        tasks = [single_request() for _ in range(n)]
        outcomes = await asyncio.gather(*tasks)
        wall_time = (time.perf_counter() - t0) * 1000

        successes = sum(1 for ok, _ in outcomes if ok)
        latencies = [ms for _, ms in outcomes]
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        max_lat = max(latencies) if latencies else 0
        min_lat = min(latencies) if latencies else 0

        result = BenchResult(
            test_name=f"concurrency_{n}",
            success=successes == n,
            total_ms=wall_time,
            extra={
                "concurrency": n,
                "successes": successes,
                "failures": n - successes,
                "avg_latency_ms": round(avg_lat, 1),
                "min_latency_ms": round(min_lat, 1),
                "max_latency_ms": round(max_lat, 1),
                "qps": round(successes / (wall_time / 1000), 2) if wall_time > 0 else 0,
            },
        )
        results.append(result)
        logger.info(
            f"   成功={successes}/{n} | 墙钟={wall_time:.0f}ms | "
            f"平均={avg_lat:.0f}ms | QPS={result.extra['qps']}"
        )

    return results


# ─── 4. 双进程互相对话 ───────────────────────────────────────────

async def test_dual_conversation(
    client: httpx.AsyncClient,
    rounds: int = 5,
) -> list[BenchResult]:
    """两个 AI 角色互相对话，测试多轮上下文和持续负载"""
    results: list[BenchResult] = []

    history_a: list[dict[str, str]] = [
        {"role": "system", "content": (
            "你是中国最顶尖的诉讼律师，有30年一线庭审经验，代理过无数重大商事、刑事案件。"
            "你深刻理解司法实践的痛点：证据整理耗时、庭审准备繁琐、法条检索低效、当事人沟通成本高。"
            "你正在和一位顶尖程序员探讨法律科技的落地方向。"
            "你必须用中文回复，每次回复200字以内，直接表达观点，不要输出思考过程。"
            "要具体、务实，结合真实诉讼场景提出需求和痛点。"
        )},
    ]
    history_b: list[dict[str, str]] = [
        {"role": "system", "content": (
            "你是硅谷顶尖全栈程序员，精通AI/ML、大语言模型、RAG、知识图谱、OCR、自动化工作流等技术。"
            "你正在和一位顶尖诉讼律师探讨法律科技的落地方向。"
            "你必须用中文回复，每次回复200字以内，直接表达观点，不要输出思考过程。"
            "要具体说明技术实现路径、难点和可行性，不说空话。"
        )},
    ]

    # 起始话题
    current_msg = (
        "我们来聊聊法律科技。作为一线律师，我每天最大的痛苦是证据整理——"
        "一个案子动辄几百份文件，光是归类、提取关键信息就要耗费大量时间。"
        "你觉得技术上能怎么解决这个问题？有没有真正能落地的方案？"
    )

    for i in range(rounds):
        # A 说
        history_a.append({"role": "user", "content": current_msg})
        payload_a = build_payload(history_a, max_tokens=2048, temperature=0.8, thinking=False)
        t0 = time.perf_counter()
        try:
            resp_a = await client.post(BASE_URL, json=payload_a, timeout=120)
            ms_a = (time.perf_counter() - t0) * 1000
            if resp_a.status_code == 200:
                reply_a = resp_a.json()["choices"][0]["message"]["content"]
                clean_a = strip_thinking(reply_a)
                history_a.append({"role": "assistant", "content": clean_a})
                logger.info(f"⚖️  律师(轮{i+1}) [{ms_a:.0f}ms]:\n{clean_a}\n")
            else:
                clean_a = f"[ERROR {resp_a.status_code}]"
                logger.warning(f"律师请求失败: {resp_a.status_code}")
        except Exception as e:
            clean_a = f"[EXCEPTION: {e}]"
            ms_a = (time.perf_counter() - t0) * 1000
            logger.error(f"律师异常: {e}")

        # B 回复 A 的话（传过滤后的干净内容）
        history_b.append({"role": "user", "content": clean_a})
        payload_b = build_payload(history_b, max_tokens=2048, temperature=0.8, thinking=False)
        t0 = time.perf_counter()
        try:
            resp_b = await client.post(BASE_URL, json=payload_b, timeout=120)
            ms_b = (time.perf_counter() - t0) * 1000
            if resp_b.status_code == 200:
                reply_b = resp_b.json()["choices"][0]["message"]["content"]
                clean_b = strip_thinking(reply_b)
                history_b.append({"role": "assistant", "content": clean_b})
                logger.info(f"[程序员](轮{i+1}) [{ms_b:.0f}ms]:\n{clean_b}\n")
            else:
                clean_b = f"[ERROR {resp_b.status_code}]"
                logger.warning(f"程序员请求失败: {resp_b.status_code}")
        except Exception as e:
            clean_b = f"[EXCEPTION: {e}]"
            ms_b = (time.perf_counter() - t0) * 1000
            logger.error(f"程序员异常: {e}")

        current_msg = clean_b  # 下一轮传干净内容

        results.append(BenchResult(
            test_name=f"dual_round_{i+1}",
            success="ERROR" not in clean_a and "ERROR" not in clean_b,
            total_ms=ms_a + ms_b,
            extra={
                "round": i + 1,
                "lawyer_ms": round(ms_a, 1),
                "programmer_ms": round(ms_b, 1),
                "a_history_len": len(history_a),
                "b_history_len": len(history_b),
            },
        ))

    return results


# ─── 主入口 ──────────────────────────────────────────────────────

async def main(tests: list[str], loop: bool = False, rounds: int = 10000) -> None:
    run_count = 0

    async with httpx.AsyncClient(headers=HEADERS) as client:
        # 先做个连通性检查
        logger.info("🔗 连通性检查...")
        try:
            resp = await client.post(
                BASE_URL,
                json=build_payload([{"role": "user", "content": "hi"}], max_tokens=8),
                timeout=30,
            )
            if resp.status_code != 200:
                logger.error(f"连接失败: {resp.status_code} {resp.text[:200]}")
                return
            logger.info("✅ 连接正常")
        except Exception as e:
            logger.error(f"无法连接: {e}")
            return

        while True:
            run_count += 1
            all_results: list[BenchResult] = []
            logger.info(f"\n{'#' * 60}")
            logger.info(f"🚀 第 {run_count} 轮测试开始")
            logger.info(f"{'#' * 60}")
            round_start = time.perf_counter()

            if "context" in tests:
                logger.info("\n" + "=" * 60)
                logger.info("📏 测试 1: 上下文长度探测")
                logger.info("=" * 60)
                all_results.extend(await test_context_length(client))

            if "speed" in tests:
                logger.info("\n" + "=" * 60)
                logger.info("⚡ 测试 2: 响应速度")
                logger.info("=" * 60)
                all_results.extend(await test_speed(client))

            if "concurrency" in tests:
                logger.info("\n" + "=" * 60)
                logger.info("🔥 测试 3: 并发压力")
                logger.info("=" * 60)
                all_results.extend(await test_concurrency(client))

            if "dual" in tests:
                logger.info("\n" + "=" * 60)
                logger.info("🧠🔬 测试 4: 双AI对话")
                logger.info("=" * 60)
                all_results.extend(await test_dual_conversation(client, rounds=rounds))

            round_elapsed = time.perf_counter() - round_start

            # 汇总
            logger.info("\n" + "=" * 60)
            logger.info(f"📊 第 {run_count} 轮测试汇总 (耗时 {round_elapsed:.1f}s)")
            logger.info("=" * 60)
            for r in all_results:
                status = "✅" if r.success else "❌"
                info = f"{status} {r.test_name}"
                if r.total_ms:
                    info += f" | {r.total_ms:.0f}ms"
                if r.tokens_per_sec:
                    info += f" | {r.tokens_per_sec:.1f} tok/s"
                if r.first_token_ms:
                    info += f" | 首token {r.first_token_ms:.0f}ms"
                if r.extra:
                    info += f" | {r.extra}"
                logger.info(info)

            if not loop:
                break

            logger.info(f"\n⏳ 10秒后开始第 {run_count + 1} 轮... (Ctrl+C 停止)")
            await asyncio.sleep(10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM 压力测试")
    parser.add_argument(
        "--tests",
        nargs="+",
        default=["context", "speed", "concurrency", "dual"],
        choices=["context", "speed", "concurrency", "dual"],
        help="选择要运行的测试",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=10000,
        help="双AI对话轮数 (默认 10000)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="循环运行直到 Ctrl+C 停止",
    )
    args = parser.parse_args()
    try:
        asyncio.run(main(args.tests, loop=args.loop, rounds=args.rounds))
    except KeyboardInterrupt:
        logger.info("\n👋 测试已手动停止")
