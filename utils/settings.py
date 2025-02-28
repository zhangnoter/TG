import os
import logging

from utils.file_creator import create_default_configs

logger = logging.getLogger(__name__)

def load_ai_models():
    """加载AI模型列表"""
    try:
        models_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'ai_models.txt')
        if not os.path.exists(models_path):
            create_default_configs()
            
        with open(models_path, 'r', encoding='utf-8') as f:
            models = [line.strip() for line in f if line.strip()]
            if models:
                return models
    except (FileNotFoundError, IOError) as e:
        logger.warning(f"ai_models.txt 加载失败: {e}，使用默认模型列表")
    return ['gpt-3.5-turbo', 'gpt-4', 'gemini-2.0-flash']

def load_summary_times():
    """加载总结时间列表"""
    try:
        times_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'summary_times.txt')
        if not os.path.exists(times_path):
            create_default_configs()
            
        with open(times_path, 'r', encoding='utf-8') as f:
            times = [line.strip() for line in f if line.strip()]
            if times:
                return times
    except (FileNotFoundError, IOError) as e:
        logger.warning(f"summary_times.txt 加载失败: {e}，使用默认时间列表")
    return ['00:00', '06:00', '12:00', '18:00']

def load_delay_times():
    """加载延迟时间列表"""
    try:
        times_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'delay_times.txt')
        if not os.path.exists(times_path):
            create_default_configs()
            
        with open(times_path, 'r', encoding='utf-8') as f:
            times = [line.strip() for line in f if line.strip()]
            if times:
                return times
    except (FileNotFoundError, IOError) as e:
        logger.warning(f"delay_times.txt 加载失败: {e}，使用默认时间列表")
    return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]