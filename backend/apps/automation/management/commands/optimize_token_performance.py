"""
Token性能优化管理命令

定期清理历史记录、优化缓存、检查系统健康状态。
"""
import asyncio
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.automation.services.token.history_recorder import history_recorder
from apps.automation.services.token.cache_manager import cache_manager
from apps.automation.services.token.performance_monitor import performance_monitor
from apps.automation.services.token.concurrency_optimizer import concurrency_optimizer

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Token获取服务性能优化和维护'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup-days',
            type=int,
            default=30,
            help='清理多少天前的历史记录（默认30天）'
        )
        parser.add_argument(
            '--warm-cache',
            nargs='*',
            help='预热指定网站的缓存（不指定则跳过）'
        )
        parser.add_argument(
            '--health-check',
            action='store_true',
            help='执行健康检查'
        )
        parser.add_argument(
            '--optimize-concurrency',
            action='store_true',
            help='分析并优化并发配置'
        )
        parser.add_argument(
            '--reset-metrics',
            action='store_true',
            help='重置性能指标'
        )

    def handle(self, *args, **options):
        """执行优化任务"""
        self.stdout.write(
            self.style.SUCCESS(f'开始Token性能优化任务 - {timezone.now()}')
        )
        
        # 运行异步任务
        asyncio.run(self._run_optimization_tasks(options))
        
        self.stdout.write(
            self.style.SUCCESS(f'Token性能优化任务完成 - {timezone.now()}')
        )

    async def _run_optimization_tasks(self, options):
        """运行优化任务"""
        
        # 1. 清理历史记录
        if options['cleanup_days'] > 0:
            self.stdout.write('正在清理历史记录...')
            try:
                deleted_count = await history_recorder.cleanup_old_records(
                    days=options['cleanup_days']
                )
                self.stdout.write(
                    self.style.SUCCESS(f'清理了 {deleted_count} 条历史记录')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'清理历史记录失败: {e}')
                )
        
        # 2. 预热缓存
        if options['warm_cache'] is not None:
            for site_name in options['warm_cache']:
                self.stdout.write(f'正在预热 {site_name} 的缓存...')
                try:
                    cache_manager.warm_up_cache(site_name)
                    self.stdout.write(
                        self.style.SUCCESS(f'{site_name} 缓存预热完成')
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'{site_name} 缓存预热失败: {e}')
                    )
        
        # 3. 健康检查
        if options['health_check']:
            self.stdout.write('正在执行健康检查...')
            try:
                health_report = performance_monitor.check_health()
                
                self.stdout.write(f"系统状态: {health_report['status']}")
                
                if health_report['alerts']:
                    self.stdout.write(
                        self.style.WARNING(f"发现 {len(health_report['alerts'])} 个告警:")
                    )
                    for alert in health_report['alerts']:
                        severity_style = {
                            'high': self.style.ERROR,
                            'medium': self.style.WARNING,
                            'low': self.style.NOTICE
                        }.get(alert['severity'], self.style.NOTICE)
                        
                        self.stdout.write(
                            severity_style(f"  [{alert['severity'].upper()}] {alert['message']}")
                        )
                else:
                    self.stdout.write(
                        self.style.SUCCESS("系统健康，无告警")
                    )
                
                # 显示关键指标
                metrics = health_report['metrics']
                self.stdout.write(f"成功率: {metrics['success_rate']:.1f}%")
                self.stdout.write(f"平均耗时: {metrics['avg_duration']:.1f}秒")
                self.stdout.write(f"并发数: {metrics['concurrent_acquisitions']}")
                self.stdout.write(f"缓存命中率: {metrics['cache_hit_rate']:.1f}%")
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'健康检查失败: {e}')
                )
        
        # 4. 并发优化分析
        if options['optimize_concurrency']:
            self.stdout.write('正在分析并发配置...')
            try:
                optimization_result = await concurrency_optimizer.optimize_concurrency()
                
                if optimization_result['recommendations']:
                    self.stdout.write(
                        self.style.WARNING(f"发现 {len(optimization_result['recommendations'])} 个优化建议:")
                    )
                    for rec in optimization_result['recommendations']:
                        self.stdout.write(f"  - {rec['reason']}")
                        if 'recommended' in rec:
                            self.stdout.write(f"    建议: {rec['recommended']}")
                else:
                    self.stdout.write(
                        self.style.SUCCESS("并发配置已优化，无需调整")
                    )
                
                # 显示资源使用情况
                usage = optimization_result['current_usage']
                self.stdout.write(f"当前并发数: {usage['total_acquisitions']}")
                self.stdout.write(f"队列大小: {usage['queue_size']}")
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'并发优化分析失败: {e}')
                )
        
        # 5. 重置性能指标
        if options['reset_metrics']:
            self.stdout.write('正在重置性能指标...')
            try:
                performance_monitor.reset_metrics()
                self.stdout.write(
                    self.style.SUCCESS('性能指标已重置')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'重置性能指标失败: {e}')
                )
        
        # 6. 清理并发资源
        self.stdout.write('正在清理并发资源...')
        try:
            await concurrency_optimizer.cleanup_resources()
            self.stdout.write(
                self.style.SUCCESS('并发资源清理完成')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'清理并发资源失败: {e}')
            )
        
        # 7. 显示最终统计
        self.stdout.write('\n=== 最终统计 ===')
        try:
            recent_stats = await history_recorder.get_recent_statistics(hours=24)
            self.stdout.write(f"最近24小时获取次数: {recent_stats['total_acquisitions']}")
            self.stdout.write(f"成功率: {recent_stats['success_rate']:.1f}%")
            self.stdout.write(f"平均耗时: {recent_stats['avg_duration']:.1f}秒")
            
            cache_stats = cache_manager.get_cache_statistics()
            self.stdout.write(f"缓存后端: {cache_stats.get('cache_backend', 'unknown')}")
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'获取统计信息失败: {e}')
            )