import os
import re
from urlextract import URLExtract
from ai import get_ai_provider
import logging

logger = logging.getLogger(__name__)

#传入字符串，返回字符串

#匹配前处理字符串
async def pre_handle(message: str) -> str:

    # 去除 markdown 链接格式，包括带单星号和双星号的，只去除紧贴着方括号的星号
    message = re.sub(r'\[(\*{1,2})?(.+?)(\*{1,2})?\]\(.+?\)', r'\2', message)
    
    # 使用 urlextract 提取链接，删除括号内的链接及括号
    extractor = URLExtract()
    urls = extractor.find_urls(message)
    for url in urls:
        # 检查链接是否在括号内
        if f"({url})" in message:
            message = message.replace(f"({url})", "")
    
    return message

async def ai_handle(message: str, rule) -> str:
    """使用AI处理消息
    
    Args:
        message: 原始消息文本
        rule: 转发规则对象，包含AI相关设置
        
    Returns:
        str: 处理后的消息文本
    """
    try:
        if not rule.is_ai:
            logger.info("AI处理未开启，返回原始消息")
            return message
        # 先读取数据库，如果ai模型为空，则使用.env中的默认模型
        if not rule.ai_model:
            rule.ai_model = os.getenv('DEFAULT_AI_MODEL')
            logger.info(f"使用默认AI模型: {rule.ai_model}")
        else:
            logger.info(f"使用规则配置的AI模型: {rule.ai_model}")
            
        provider = await get_ai_provider(rule.ai_model)
        
        if not rule.ai_prompt:
            rule.ai_prompt = os.getenv('DEFAULT_AI_PROMPT')
            logger.info("使用默认AI提示词")
        else:
            logger.info("使用规则配置的AI提示词")
        
        if '{Message}'  in rule.ai_prompt:
            # 把提示词里的{Message}替换为message
            rule.ai_prompt = rule.ai_prompt.replace('{Message}', message)
            logger.info(f"处理后的AI提示词: {rule.ai_prompt}")
            
        logger.info(f"提示词: {rule.ai_prompt}")
        processed_text = await provider.process_message(
            message=message,
            prompt=rule.ai_prompt,
            model=rule.ai_model
        )
        logger.info(f"AI处理完成: {processed_text}")
        return processed_text
        
    except Exception as e:
        logger.error(f"AI处理消息时出错: {str(e)}")
        return message  # 出错时返回原始消息
