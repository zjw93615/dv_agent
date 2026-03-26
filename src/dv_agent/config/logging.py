"""
日志配置模块
使用structlog实现结构化日志
"""

import sys
import logging
from typing import Optional

import structlog
from structlog.types import Processor


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    add_timestamp: bool = True,
) -> None:
    """
    配置结构化日志
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        json_format: 是否输出JSON格式
        add_timestamp: 是否添加时间戳
    """
    # 设置标准库日志级别
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )
    
    # 构建处理器链
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    if add_timestamp:
        shared_processors.insert(0, structlog.processors.TimeStamper(fmt="iso"))
    
    if json_format:
        # JSON格式（生产环境）
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        # 控制台格式（开发环境）
        shared_processors.append(structlog.dev.set_exc_info)
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # 配置格式化器
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    
    # 应用到根日志处理器
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """
    获取日志记录器
    
    Args:
        name: 日志记录器名称，默认为调用模块名
        
    Returns:
        结构化日志记录器
    """
    return structlog.get_logger(name)


# 常用日志上下文绑定
def bind_request_context(
    request_id: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    """绑定请求上下文到日志"""
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
    )


def clear_request_context() -> None:
    """清除请求上下文"""
    structlog.contextvars.clear_contextvars()
