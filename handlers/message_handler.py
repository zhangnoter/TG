import os
import re
from urlextract import URLExtract
from ai import get_ai_provider
import logging
import asyncio

logger = logging.getLogger(__name__)

#传入字符串，返回字符串

#匹配前处理字符串
async def pre_handle(message: str) -> str:

    # 去除 markdown 链接格式，包括带单星号和双星号的，只去除紧贴着方括号的星号
    message = re.sub(r'\[(\*{1,2})?(.+?)(\*{1,2})?\]\(.+?\)', r'\2', message)
    
    # # 使用 urlextract 提取链接，删除括号内的链接及括号
    # extractor = URLExtract()
    # urls = extractor.find_urls(message)
    # for url in urls:
    #     # 检查链接是否在括号内
    #     if f"({url})" in message:
    #         message = message.replace(f"({url})", "")
    
    return message

async def get_chat_messages(client, chat_id, minutes=None, count=None, delay_seconds: float = 0.5) -> str:
    """获取聊天记录
    
    Args:
        client: Telegram客户端
        chat_id: 聊天ID
        minutes: 获取最近几分钟的消息
        count: 获取最新的几条消息
        delay_seconds: 每条消息获取之间的延迟秒数，默认0.5秒
        
    Returns:
        str: 聊天记录文本
    """
    try:
        messages = []
        limit = count if count else 500  # 设置一个合理的默认值
        processed_count = 0
        
        if minutes:
            # 计算时间范围
            from datetime import datetime, timedelta
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=minutes)
            
            # 获取指定时间范围内的消息
            async for message in client.iter_messages(
                chat_id,
                limit=limit,
                offset_date=end_time,
                reverse=True
            ):
                if message.date < start_time:
                    break
                if message.text:
                    messages.append(message.text)
                    processed_count += 1
                    if processed_count % 20 == 0:  # 每处理20条消息休息一次
                        await asyncio.sleep(delay_seconds)
        else:
            # 获取指定数量的最新消息
            async for message in client.iter_messages(
                chat_id,
                limit=count
            ):
                if message.text:
                    messages.append(message.text)
                    processed_count += 1
                    if processed_count % 20 == 0:  # 每处理20条消息休息一次
                        await asyncio.sleep(delay_seconds)
                
        return "\n---\n".join(messages) if messages else ""
        
    except Exception as e:
        logger.error(f"获取聊天记录时出错: {str(e)}")
        return ""

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
        
        # 处理特殊提示词格式
        prompt = rule.ai_prompt
        if prompt:
            # 处理聊天记录提示词
            import re
            # 匹配源聊天和目标聊天的context格式
            source_context_match = re.search(r'\{source_message_context:(\d+)\}', prompt)
            target_context_match = re.search(r'\{target_message_context:(\d+)\}', prompt)
            # 匹配源聊天和目标聊天的time格式
            source_time_match = re.search(r'\{source_message_time:(\d+)\}', prompt)
            target_time_match = re.search(r'\{target_message_time:(\d+)\}', prompt)
            
            if any([source_context_match, target_context_match, source_time_match, target_time_match]):
                from utils.common import get_main_module
                main = await get_main_module()
                client = main.user_client
                
                # 获取源聊天和目标聊天ID
                source_chat_id = int(rule.source_chat.telegram_chat_id)
                target_chat_id = int(rule.target_chat.telegram_chat_id)
                
                # 处理源聊天的消息获取
                if source_context_match:
                    count = int(source_context_match.group(1))
                    chat_history = await get_chat_messages(client, source_chat_id, count=count)
                    prompt = prompt.replace(source_context_match.group(0), chat_history)
                    
                if source_time_match:
                    minutes = int(source_time_match.group(1))
                    chat_history = await get_chat_messages(client, source_chat_id, minutes=minutes)
                    prompt = prompt.replace(source_time_match.group(0), chat_history)
                
                # 处理目标聊天的消息获取
                if target_context_match:
                    count = int(target_context_match.group(1))
                    chat_history = await get_chat_messages(client, target_chat_id, count=count)
                    prompt = prompt.replace(target_context_match.group(0), chat_history)
                    
                if target_time_match:
                    minutes = int(target_time_match.group(1))
                    chat_history = await get_chat_messages(client, target_chat_id, minutes=minutes)
                    prompt = prompt.replace(target_time_match.group(0), chat_history)
            
            # 替换消息占位符
            if '{Message}' in prompt:
                prompt = prompt.replace('{Message}', message)
                
        logger.info(f"处理后的AI提示词: {prompt}")
        processed_text = await provider.process_message(
            message=message,
            prompt=prompt,
            model=rule.ai_model
        )
        logger.info(f"AI处理完成: {processed_text}")
        return processed_text
        
    except Exception as e:
        logger.error(f"AI处理消息时出错: {str(e)}")
        return message  
