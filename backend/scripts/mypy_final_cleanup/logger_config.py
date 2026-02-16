"""LoggerConfig - 配置日志记录"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def setup_logger(
    name: str = "mypy_final_cleanup",
    log_dir: Path | None = None,
    level: int = logging.INFO
) -> logging.Logger:
    """
    配置日志记录器
    
    Args:
        name: 日志记录器名称
        log_dir: 日志目录路径，默认为backend/logs
        level: 日志级别
        
    Returns:
        配置好的日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 确定日志目录
    if log_dir is None:
        # 默认路径：scripts/mypy_final_cleanup -> scripts -> backend -> logs
        backend_path = Path(__file__).parent.parent.parent
        log_dir = backend_path / "logs"
    
    log_dir.mkdir(exist_ok=True)
    
    # 创建日志文件（使用时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{name}_{timestamp}.log"
    
    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    # 格式化器
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"日志记录器已配置，日志文件: {log_file}")
    
    return logger
