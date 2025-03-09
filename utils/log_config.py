import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv
from utils.constants import LOG_MAX_SIZE_MB, LOG_BACKUP_COUNT

def setup_logging():
    """
    配置日志系统，将所有日志输出到根目录下的logs文件夹，
    单个日志文件大小和数量由环境变量控制
    """
    # 加载环境变量
    load_dotenv()
    
    # 从环境变量获取日志配置，如果没有则使用默认值
    log_max_size = LOG_MAX_SIZE_MB * 1024 * 1024  # 默认30MB
    log_backup_count = LOG_BACKUP_COUNT  # 默认保留3个备份
    
    # 确保logs目录存在
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 创建日志文件路径
    log_file = log_dir / "telegram_forwarder.log"
    
    # 创建根日志记录器
    root_logger = logging.getLogger()
    
    # 设置日志级别 - 默认使用INFO级别（调试模式）
    root_logger.setLevel(logging.INFO)
    
    # 创建一个处理器，用于将日志写入文件
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=log_max_size,
        backupCount=log_backup_count,
        encoding='utf-8'
    )
    
    # 创建一个处理器，用于将日志输出到控制台
    console_handler = logging.StreamHandler()
    
    # 创建格式化器
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 将格式化器添加到处理器
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 将处理器添加到根日志记录器
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # 返回配置的日志记录器
    return root_logger 