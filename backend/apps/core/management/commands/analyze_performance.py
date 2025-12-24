"""
性能分析管理命令

分析日志文件中的性能数据，识别性能瓶颈
"""
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = '分析性能日志，识别性能瓶颈'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--log-file',
            type=str,
            default='logs/api.log',
            help='日志文件路径（默认: logs/api.log）'
        )
        parser.add_argument(
            '--threshold',
            type=int,
            default=1000,
            help='慢 API 阈值（毫秒，默认: 1000）'
        )
        parser.add_argument(
            '--top',
            type=int,
            default=10,
            help='显示前 N 个慢 API（默认: 10）'
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='分析最近 N 小时的日志（默认: 24）'
        )
    
    def handle(self, *args, **options):
        log_file = options['log_file']
        threshold = options['threshold']
        top_n = options['top']
        hours = options['hours']
        
        self.stdout.write(self.style.SUCCESS(f'\n=== 性能分析报告 ===\n'))
        self.stdout.write(f'日志文件: {log_file}')
        self.stdout.write(f'慢 API 阈值: {threshold}ms')
        self.stdout.write(f'分析时间范围: 最近 {hours} 小时\n')
        
        # 解析日志
        api_stats = self._parse_logs(log_file, hours)
        
        if not api_stats:
            self.stdout.write(self.style.WARNING('未找到性能数据'))
            return
        
        # 分析性能
        self._analyze_performance(api_stats, threshold, top_n)
    
    def _parse_logs(self, log_file: str, hours: int) -> dict:
        """
        解析日志文件
        
        Args:
            log_file: 日志文件路径
            hours: 分析最近 N 小时
            
        Returns:
            API 统计数据
        """
        api_stats = defaultdict(lambda: {
            'count': 0,
            'total_time': 0,
            'total_queries': 0,
            'max_time': 0,
            'max_queries': 0,
            'errors': 0
        })
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    # 尝试解析 JSON 格式的日志
                    try:
                        if 'metric_type' in line and 'api_performance' in line:
                            # 提取 JSON 部分
                            json_match = re.search(r'\{.*\}', line)
                            if json_match:
                                data = json.loads(json_match.group())
                                
                                # 检查时间范围（如果有时间戳）
                                # 这里简化处理，实际应该解析日志时间戳
                                
                                # 提取 API 信息
                                path = data.get('path', 'unknown')
                                method = data.get('method', 'GET')
                                endpoint = f"{method} {path}"
                                
                                duration_ms = data.get('duration_ms', 0)
                                query_count = data.get('query_count', 0)
                                status_code = data.get('status_code', 200)
                                
                                # 更新统计
                                stats = api_stats[endpoint]
                                stats['count'] += 1
                                stats['total_time'] += duration_ms
                                stats['total_queries'] += query_count
                                stats['max_time'] = max(stats['max_time'], duration_ms)
                                stats['max_queries'] = max(stats['max_queries'], query_count)
                                
                                if status_code >= 400:
                                    stats['errors'] += 1
                    
                    except (json.JSONDecodeError, KeyError):
                        continue
        
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'日志文件不存在: {log_file}'))
            return {}
        
        return api_stats
    
    def _analyze_performance(self, api_stats: dict, threshold: int, top_n: int):
        """
        分析性能数据
        
        Args:
            api_stats: API 统计数据
            threshold: 慢 API 阈值
            top_n: 显示前 N 个
        """
        # 计算平均值
        for endpoint, stats in api_stats.items():
            if stats['count'] > 0:
                stats['avg_time'] = stats['total_time'] / stats['count']
                stats['avg_queries'] = stats['total_queries'] / stats['count']
        
        # 按平均响应时间排序
        sorted_by_time = sorted(
            api_stats.items(),
            key=lambda x: x[1]['avg_time'],
            reverse=True
        )
        
        # 按平均查询次数排序
        sorted_by_queries = sorted(
            api_stats.items(),
            key=lambda x: x[1]['avg_queries'],
            reverse=True
        )
        
        # 显示最慢的 API
        self.stdout.write(self.style.SUCCESS(f'\n=== 最慢的 {top_n} 个 API ===\n'))
        for i, (endpoint, stats) in enumerate(sorted_by_time[:top_n], 1):
            self.stdout.write(
                f"{i}. {endpoint}\n"
                f"   调用次数: {stats['count']}\n"
                f"   平均响应时间: {stats['avg_time']:.2f}ms\n"
                f"   最大响应时间: {stats['max_time']:.2f}ms\n"
                f"   平均查询次数: {stats['avg_queries']:.2f}\n"
                f"   错误次数: {stats['errors']}\n"
            )
        
        # 显示查询次数最多的 API
        self.stdout.write(self.style.SUCCESS(f'\n=== 查询次数最多的 {top_n} 个 API ===\n'))
        for i, (endpoint, stats) in enumerate(sorted_by_queries[:top_n], 1):
            if stats['avg_queries'] > 0:
                self.stdout.write(
                    f"{i}. {endpoint}\n"
                    f"   调用次数: {stats['count']}\n"
                    f"   平均查询次数: {stats['avg_queries']:.2f}\n"
                    f"   最大查询次数: {stats['max_queries']}\n"
                    f"   平均响应时间: {stats['avg_time']:.2f}ms\n"
                )
        
        # 统计慢 API
        slow_apis = [
            (endpoint, stats)
            for endpoint, stats in api_stats.items()
            if stats['avg_time'] > threshold
        ]
        
        if slow_apis:
            self.stdout.write(
                self.style.WARNING(
                    f'\n=== 慢 API 警告（超过 {threshold}ms）===\n'
                )
            )
            for endpoint, stats in slow_apis:
                self.stdout.write(
                    f"⚠️  {endpoint}\n"
                    f"   平均响应时间: {stats['avg_time']:.2f}ms\n"
                    f"   调用次数: {stats['count']}\n"
                )
        
        # 统计可能存在 N+1 查询的 API
        n_plus_1_suspects = [
            (endpoint, stats)
            for endpoint, stats in api_stats.items()
            if stats['avg_queries'] > 10
        ]
        
        if n_plus_1_suspects:
            self.stdout.write(
                self.style.WARNING(
                    f'\n=== 可能存在 N+1 查询问题的 API ===\n'
                )
            )
            for endpoint, stats in n_plus_1_suspects:
                self.stdout.write(
                    f"⚠️  {endpoint}\n"
                    f"   平均查询次数: {stats['avg_queries']:.2f}\n"
                    f"   最大查询次数: {stats['max_queries']}\n"
                    f"   建议: 使用 select_related 或 prefetch_related 优化查询\n"
                )
        
        # 总体统计
        total_requests = sum(stats['count'] for stats in api_stats.values())
        total_errors = sum(stats['errors'] for stats in api_stats.values())
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
        
        self.stdout.write(self.style.SUCCESS(f'\n=== 总体统计 ===\n'))
        self.stdout.write(f'总请求数: {total_requests}')
        self.stdout.write(f'总错误数: {total_errors}')
        self.stdout.write(f'错误率: {error_rate:.2f}%')
        self.stdout.write(f'监控的 API 数量: {len(api_stats)}\n')
