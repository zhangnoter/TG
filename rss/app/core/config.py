import os
from dotenv import load_dotenv
import pytz
from pathlib import Path
import logging

# 加载环境变量
load_dotenv()

class Settings:
    PROJECT_NAME: str = "TG Forwarder RSS"
    DEFAULT_TIMEZONE = pytz.timezone(os.getenv('DEFAULT_TIMEZONE', 'Asia/Shanghai'))
    HOST: str = os.getenv("RSS_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("RSS_PORT", "8000"))
    
    # 数据存储路径
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
    DATA_PATH: str = os.path.join(BASE_DIR, "./rss/data")
    
    # 媒体文件存储路径，确保与RSSFilter中使用的路径一致
    RSS_MEDIA_PATH = os.getenv("RSS_MEDIA_PATH", "./rss/media")
    # 转换为绝对路径，确保能正确找到文件
    MEDIA_PATH: str = os.path.abspath(os.path.join(BASE_DIR, RSS_MEDIA_PATH) 
                                      if not os.path.isabs(RSS_MEDIA_PATH) 
                                      else RSS_MEDIA_PATH)
    
    # 每个规则最大保存条目数
    MAX_ITEMS_PER_RULE: int = int(os.getenv("DEFAULT_RSS_MAX_ITEMS", "20"))
    
    # 确保目录存在
    def __init__(self):
        os.makedirs(self.DATA_PATH, exist_ok=True)
        os.makedirs(self.MEDIA_PATH, exist_ok=True)
        logger = logging.getLogger(__name__)
        logger.info(f"媒体文件路径: {self.MEDIA_PATH}")

settings = Settings() 