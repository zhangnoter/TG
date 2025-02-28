import logging
import os
import pytz
from filters.base_filter import BaseFilter

logger = logging.getLogger(__name__)

class InfoFilter(BaseFilter):
    """
    信息过滤器，添加原始链接和发送者信息
    """
    
    async def _process(self, context):
        """
        添加原始链接和发送者信息
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 是否继续处理
        """
        rule = context.rule
        event = context.event
        
        # 添加原始链接
        if rule.is_original_link:
            context.original_link = f"\n\n原始消息: https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
            logger.info(f'添加原始链接: {context.original_link}')
        
        # 添加发送者信息（如果在过滤器链中已经有KeywordFilter处理了发送者信息，这里就跳过）
        if rule.is_original_sender and event.sender and not context.sender_info:
            try:
                sender_name = (
                    event.sender.title if hasattr(event.sender, 'title')
                    else f"{event.sender.first_name or ''} {event.sender.last_name or ''}".strip()
                )
                context.sender_info = f"{sender_name}\n\n"
                logger.info(f'添加发送者信息: {context.sender_info}')
            except Exception as e:
                logger.error(f'获取发送者信息出错: {str(e)}')
        
        # 添加时间信息
        if rule.is_original_time:
            try:
                # 创建时区对象
                timezone = pytz.timezone(os.getenv('DEFAULT_TIMEZONE', 'Asia/Shanghai'))
                local_time = event.message.date.astimezone(timezone)
                context.time_info = f"\n\n{local_time.strftime('%Y-%m-%d %H:%M:%S')}"
                logger.info(f'添加时间信息: {context.time_info}')
            except Exception as e:
                logger.error(f'处理时间信息时出错: {str(e)}')
        
        return True 