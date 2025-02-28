import logging
import os
from filters.base_filter import BaseFilter
from enums.enums import HandleMode, PreviewMode
from utils.common import get_main_module
from telethon.tl.types import Channel

logger = logging.getLogger(__name__)

class EditFilter(BaseFilter):
    """
    编辑过滤器，用于在编辑模式下修改原始消息
    仅在频道消息中生效
    """
    
    async def _process(self, context):
        """
        处理消息编辑
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 是否继续处理
        """
        rule = context.rule
        event = context.event
        
        # 如果不是编辑模式，继续后续处理
        if rule.handle_mode != HandleMode.EDIT:
            return True
            
        # 检查是否为频道消息
        chat = await event.get_chat()
        if not isinstance(chat, Channel):
            logger.info("不是频道消息，跳过编辑")
            return False
            
        try:
            # 获取用户客户端
            main = await get_main_module()
            user_client = main.user_client if (main and hasattr(main, 'user_client')) else None
            
            if not user_client:
                logger.error("无法获取用户客户端，无法执行编辑操作")
                return False
                
            # 根据预览模式设置 link_preview
            link_preview = {
                PreviewMode.ON: True,
                PreviewMode.OFF: False,
                PreviewMode.FOLLOW: event.message.media is not None  # 跟随原消息
            }[rule.is_preview]
            
            # 组合消息文本
            message_text = context.sender_info + context.message_text + context.time_info + context.original_link
            
            # 检查文本是否有变化
            if message_text == event.message.text:
                logger.info("消息文本没有变化，跳过编辑")
                return False
            
            # 处理媒体组消息
            if context.is_media_group:
                # 尝试编辑媒体组中的每条消息
                for message in context.media_group_messages:
                    try:
                        # 只在第一条消息上添加文本
                        text_to_edit = message_text if message.id == event.message.id else ""
                        await user_client.edit_message(
                            event.chat_id,
                            message.id,
                            text=text_to_edit,
                            parse_mode=rule.message_mode.value,
                            link_preview=link_preview
                        )
                        logger.info(f"成功编辑媒体组消息 {message.id}")
                    except Exception as e:
                        if "was not modified" not in str(e):
                            logger.error(f"编辑媒体组消息 {message.id} 失败: {str(e)}")
                return False
            # 处理所有其他消息（包括单条媒体消息和纯文本消息）
            else:
                try:
                    await user_client.edit_message(
                        event.chat_id,
                        event.message.id,
                        text=message_text,
                        parse_mode=rule.message_mode.value,
                        link_preview=link_preview
                    )
                    logger.info(f"成功编辑消息 {event.message.id}")
                    return False
                except Exception as e:
                    if "was not modified" not in str(e):
                        logger.error(f"编辑消息失败: {str(e)}")
                    return False
                
        except Exception as e:
            logger.error(f"编辑过滤器处理出错: {str(e)}")
            return False 