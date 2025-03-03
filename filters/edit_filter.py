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
            logger.info(f"组合后的消息文本: '{message_text[:50]}...(省略)' (长度: {len(message_text)})")
            logger.info(f"原消息文本: '{event.message.text[:50]}...(省略)' (长度: {len(event.message.text or '')})")
            
            # 处理媒体组消息
            if context.is_media_group:
                logger.info(f"开始处理媒体组消息，组ID: {context.media_group_id}，共有 {len(context.media_group_messages)} 条消息")
                
                # 日志记录媒体组所有消息的概览
                media_group_overview = []
                for idx, msg in enumerate(context.media_group_messages):
                    media_type = type(msg.media).__name__ if msg.media else "无媒体"
                    has_text = "有文本" if msg.text else "无文本"
                    text_length = len(msg.text or "")
                    media_group_overview.append(f"消息{idx+1}: ID={msg.id}, 类型={media_type}, {has_text}({text_length}字)")
                
                logger.info(f"媒体组消息概览: {' | '.join(media_group_overview)}")
                
                # 尝试编辑媒体组中的每条消息
                has_text_message = None
                original_text = ""
                
                # 先找到包含文本的消息
                for message in context.media_group_messages:
                    logger.info(f"检查媒体组消息 ID: {message.id}, 文本长度: {len(message.text or '')}")
                    if message.text:
                        has_text_message = message
                        original_text = message.text or ""
                        logger.info(f"找到包含文本的消息: ID={message.id}, 文本: '{original_text[:50]}...(省略)'")
                        break
                
                # 如果没找到包含文本的消息，则默认使用第一条消息
                if not has_text_message and context.media_group_messages:
                    has_text_message = context.media_group_messages[0]
                    original_text = has_text_message.text or ""
                    logger.info(f"未找到包含文本的消息，使用第一条消息: ID={has_text_message.id}")
                
                # 检查文本是否有变化
                if message_text == original_text:
                    logger.info("媒体组消息文本没有变化，跳过编辑")
                    return False
                
                for message in context.media_group_messages:
                    try:
                        # 只在包含文本的消息上添加文本
                        is_text_message = has_text_message and message.id == has_text_message.id
                        text_to_edit = message_text if is_text_message else ""
                        
                        # 如果当前消息不是文本消息，但原本有文本，则保留其文本
                        if not is_text_message and (message.text or ""):
                            text_to_edit = message.text
                            logger.info(f"保留非主文本消息的原有文本: '{text_to_edit[:30]}...(省略)'")
                        
                        logger.info(f"准备编辑消息 ID: {message.id}, 是否为文本消息: {is_text_message}, "
                                  f"文本长度: {len(text_to_edit)}")
                        
                        await user_client.edit_message(
                            event.chat_id,
                            message.id,
                            text=text_to_edit,
                            parse_mode=rule.message_mode.value,
                            link_preview=link_preview
                        )
                        logger.info(f"成功编辑媒体组消息 {message.id}{' (文本消息)' if is_text_message else ''}")
                    except Exception as e:
                        error_msg = str(e)
                        if "was not modified" not in error_msg:
                            logger.error(f"编辑媒体组消息 {message.id} 失败: {error_msg}")
                        else:
                            logger.info(f"消息 {message.id} 未修改: {error_msg}")
                return False
            
            # 检查非媒体组消息文本是否有变化
            if message_text == event.message.text:
                logger.info("消息文本没有变化，跳过编辑")
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