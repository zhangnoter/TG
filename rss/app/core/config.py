import os
from dotenv import load_dotenv
import pytz

# 加载环境变量
load_dotenv()

class Settings:
    PROJECT_NAME: str = "TG Forwarder RSS"
    DEFAULT_TIMEZONE = pytz.timezone(os.getenv('DEFAULT_TIMEZONE', 'Asia/Shanghai'))
    HOST: str = os.getenv("RSS_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("RSS_PORT", "8000"))

settings = Settings() 