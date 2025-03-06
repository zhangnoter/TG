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

def load_max_media_size():
    """加载媒体大小限制"""
    try:
        size_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'max_media_size.txt')
        if not os.path.exists(size_path):
            create_default_configs()
            
        with open(size_path, 'r', encoding='utf-8') as f:
            size = [line.strip() for line in f if line.strip()]
            if size:
                return size
            
    except (FileNotFoundError, IOError) as e:
        logger.warning(f"max_media_size.txt 加载失败: {e}，使用默认大小限制")
    return [5,10,15,20,50,100,200,300,500,1024,2048]


def load_media_extensions():
    """加载媒体扩展名"""
    try:
        size_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'media_extensions.txt')
        if not os.path.exists(size_path):
            create_default_configs()
            
        with open(size_path, 'r', encoding='utf-8') as f:
            size = [line.strip() for line in f if line.strip()]
            if size:
                return size
            
    except (FileNotFoundError, IOError) as e:
        logger.warning(f"media_extensions.txt 加载失败: {e}，使用默认扩展名")
    return ['无扩展名','txt','jpg','png','gif','mp4','mp3','wav','ogg','flac','aac','wma','m4a','m4v','mov','avi','mkv','webm','mpg','mpeg','mpe','mp3','mp2','m4a','m4p','m4b','m4r','m4v','mpg','mpeg','mp2','mp3','mp4','mpc','oga','ogg','wav','wma','3gp','3g2','3gpp','3gpp2','amr','awb','caf','flac','m4a','m4b','m4p','oga','ogg','opus','spx','vorbis','wav','wma','webm','aac','ac3','dts','dtshd','flac','mp3','mp4','m4a','m4b','m4p','oga','ogg','wav','wma','webm','aac','ac3','dts','dtshd','flac','mp3','mp4','m4a','m4b','m4p','oga','ogg','wav','wma','webm','aac','ac3','dts','dtshd','flac','mp3','mp4','m4a','m4b','m4p','oga','ogg','wav','wma','webm','aac','ac3','dts','dtshd','flac','mp3','mp4','m4a','m4b','m4p','oga','ogg','wav','wma','webm','aac','ac3','dts','dtshd','flac','mp3','mp4','m4a','m4b','m4p','oga','ogg','wav','wma','webm']