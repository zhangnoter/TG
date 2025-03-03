import logging
import os
import asyncio
from utils.media import get_media_size
from utils.constants import TEMP_DIR
from filters.base_filter import BaseFilter
from utils.media import get_max_media_size
from enums.enums import PreviewMode

logger = logging.getLogger(__name__)

class MediaFilter(BaseFilter):
    """
    媒体过滤器，处理消息中的媒体内容
    """
    
    async def _process(self, context):
        """
        处理媒体内容
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 是否继续处理
        """
        # 确保临时目录存在
        os.makedirs(TEMP_DIR, exist_ok=True)
        
        rule = context.rule
        event = context.event
        client = context.client

        logger.info(f"MediaFilter处理消息前，context: {context.__dict__}")
        try:
            # 获取媒体大小限制
            MAX_MEDIA_SIZE = await get_max_media_size()
            
            # 如果是媒体组消息
            if event.message.grouped_id:
                logger.info(f'处理媒体组消息 组ID: {event.message.grouped_id}')
                await self._process_media_group(context, MAX_MEDIA_SIZE)
            else:
                logger.info(f'处理单条媒体消息')
                await self._process_single_media(context, MAX_MEDIA_SIZE)
            
            return True
        finally:
            logger.info(f"MediaFilter处理消息后，context: {context.__dict__}")
    
    async def _process_media_group(self, context, MAX_MEDIA_SIZE):
        """处理媒体组消息"""
        event = context.event
        client = context.client
        
        logger.info(f'处理媒体组消息 组ID: {event.message.grouped_id}')
        
        # 等待更长时间让所有媒体消息到达
        await asyncio.sleep(1)
        
        # 收集媒体组的所有消息
        try:
            async for message in event.client.iter_messages(
                event.chat_id,
                limit=20,
                min_id=event.message.id - 10,
                max_id=event.message.id + 10
            ):
                if message.grouped_id == event.message.grouped_id:
                    # 保存第一条消息的文本和按钮
                    if not context.message_text and not context.original_message_text:
                        context.message_text = message.text or ''
                        context.buttons = message.buttons if hasattr(message, 'buttons') else None
                        logger.info(f'获取到媒体组文本: {context.message_text}')
                    
                    # 检查媒体大小
                    if message.media:
                        file_size = await get_media_size(message.media)
                        if MAX_MEDIA_SIZE and file_size > MAX_MEDIA_SIZE:
                            context.skipped_media.append((message, file_size))
                            continue
                    context.media_group_messages.append(message)
                    logger.info(f'找到媒体组消息: ID={message.id}, 类型={type(message.media).__name__ if message.media else "无媒体"}')
        except Exception as e:
            logger.error(f'收集媒体组消息时出错: {str(e)}')
            context.errors.append(f"收集媒体组消息错误: {str(e)}")
        
        logger.info(f'共找到 {len(context.media_group_messages)} 条媒体组消息，{len(context.skipped_media)} 条超限')
    
    async def _process_single_media(self, context, MAX_MEDIA_SIZE):
        """处理单条媒体消息"""
        event = context.event
        
        # 检查是否是纯链接预览消息
        is_pure_link_preview = (
            event.message.media and
            hasattr(event.message.media, 'webpage') and
            not any([
                getattr(event.message.media, 'photo', None),
                getattr(event.message.media, 'document', None),
                getattr(event.message.media, 'video', None),
                getattr(event.message.media, 'audio', None),
                getattr(event.message.media, 'voice', None)
            ])
        )
        
        # 检查是否有实际媒体
        has_media = (
            event.message.media and
            any([
                getattr(event.message.media, 'photo', None),
                getattr(event.message.media, 'document', None),
                getattr(event.message.media, 'video', None),
                getattr(event.message.media, 'audio', None),
                getattr(event.message.media, 'voice', None)
            ])
        )
        
        # 处理实际媒体
        if has_media:
            # 检查媒体大小
            file_size = await get_media_size(event.message.media)
            logger.info(f'媒体文件大小: {file_size/1024/1024:.2f}MB')
            
            if MAX_MEDIA_SIZE and file_size > MAX_MEDIA_SIZE:
                logger.info(f'媒体文件超过大小限制 ({MAX_MEDIA_SIZE/1024/1024:.2f}MB)')
                context.skipped_media.append((event.message, file_size))
            else:
                try:
                    # 下载媒体文件
                    file_path = await event.message.download_media(TEMP_DIR)
                    if file_path:
                        context.media_files.append(file_path)
                        logger.info(f'媒体文件已下载到: {file_path}')
                except Exception as e:
                    logger.error(f'下载媒体文件时出错: {str(e)}')
                    context.errors.append(f"下载媒体文件错误: {str(e)}")
        elif is_pure_link_preview:
            # 记录这是纯链接预览消息
            context.is_pure_link_preview = True
            logger.info('这是一条纯链接预览消息') 