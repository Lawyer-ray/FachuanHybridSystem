"""Django management command."""
from __future__ import annotations
import asyncio
import json
import statistics
import time
import httpx
from django.core.management.base import BaseCommand, CommandError
from typing import Any
import logging
logger = logging.getLogger(__name__)

def _parse_headers(headers_kv: list[str]) -> dict[str, str]:
    """解析 Key:Value 格式的 header 列表"""
    headers: dict[str, str] = {}
    for kv in headers_kv:
        if ':' not in kv:
            raise CommandError('header 格式必须为 Key:Value')
        k, v = kv.split(':', 1)
        headers[k.strip()] = v.strip()
    return headers

def _parse_json_body(json_body: str | None) -> None:
    """解析 JSON 请求体"""
    if not json_body:
        return None
    try:
        return json.loads(json_body)
    except Exception:
        raise CommandError('--json 必须是合法 JSON 字符串') from None

class Command(BaseCommand):

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument('--url', required=True)
        parser.add_argument('--method', default='GET')
        parser.add_argument('--requests', type=int, default=50)
        parser.add_argument('--concurrency', type=int, default=10)
        parser.add_argument('--timeout', type=float, default=30.0)
        parser.add_argument('--json', dest='json_body', default=None)
        parser.add_argument('--header', action='append', default=[])

    def handle(self, *args, **options) -> None:
        url = options['url']
        method = str(options['method'] or 'GET').upper()
        total = int(options['requests'])
        concurrency = int(options['concurrency'])
        timeout = float(options['timeout'])
        if total <= 0 or concurrency <= 0:
            raise CommandError('requests/concurrency 必须为正整数')
        headers = _parse_headers(options['header'] or [])
        data = _parse_json_body(options['json_body'])

        async def run() -> None:
            sem = asyncio.Semaphore(concurrency)
            timings: list[Any] = []
            statuses: dict[int, int] = {}
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:

                async def one(i: int) -> None:
                    async with sem:
                        t0 = time.perf_counter()
                        try:
                            resp = await client.request(method, url, headers=headers, json=data)
                            ms = (time.perf_counter() - t0) * 1000.0
                            timings.append(ms)
                            statuses[resp.status_code] = statuses.get(resp.status_code, 0) + 1
                        except Exception:
                            logger.exception('操作失败')
                            ms = (time.perf_counter() - t0) * 1000.0
                            timings.append(ms)
                            statuses['error'] = statuses.get('error', 0) + 1
                await asyncio.gather(*[one(i) for i in range(total)])
            timings.sort()
            self.stdout.write(json.dumps(_build_report(url, method, total, concurrency, statuses, timings), ensure_ascii=False))
        asyncio.run(run())

def _build_report(url: Any, method: Any, total: Any, concurrency: Any, statuses: Any, timings: Any) -> None:
    """构建基准测试报告"""

    def pct(p: float) -> float:
        if not timings:
            return 0.0
        idx = min(len(timings) - 1, max(0, round(p / 100.0 * (len(timings) - 1))))
        return timings[idx]
    return {'url': url, 'method': method, 'requests': total, 'concurrency': concurrency, 'status_counts': statuses, 'latency_ms': {'min': round(timings[0], 2) if timings else None, 'p50': round(pct(50), 2), 'p95': round(pct(95), 2), 'p99': round(pct(99), 2), 'max': round(timings[-1], 2) if timings else None, 'avg': round(statistics.mean(timings), 2) if timings else None}}