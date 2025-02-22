import os
import logging

logger = logging.getLogger(__name__)


def load_ai_models():
    """加载AI模型列表"""
    try:
        # 使用正确的路径
        models_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'ai_models.txt')
        with open(models_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning("ai_models.txt 不存在，使用默认模型列表")
        return ['gpt-3.5-turbo', 'gpt-4', 'gemini-2.0-flash']

# 加载时间和时区列表
def load_summary_times():
    """加载总结时间列表"""
    try:
        times_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'summary_times.txt')
        with open(times_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning("summary_times.txt 不存在，使用默认时间")
        return ["00:00"]