import os
import logging
import asyncio
import aiohttp
import mimetypes
import json
from pathlib import Path
from datetime import datetime
import shutil
from filters.base_filter import BaseFilter
import uuid

logger = logging.getLogger(__name__)

class RSSFilter(BaseFilter):
    """
    RSS过滤器，用于将符合条件的消息添加到RSS订阅源中
    """
    
    def __init__(self):
        super().__init__()
        self.rss_enabled = os.getenv('RSS_ENABLED', '').lower() == 'true'
        self.rss_host = os.getenv('RSS_HOST', '127.0.0.1')
        self.rss_port = int(os.getenv('RSS_PORT', '8000'))
        self.rss_base_url = f"http://{self.rss_host}:{self.rss_port}"
        
        # 使用环境变量中的RSS_MEDIA_PATH
        self.rss_media_path = os.getenv('RSS_MEDIA_PATH', './rss/media')
        
        # 获取绝对路径
        if not os.path.isabs(self.rss_media_path):
            # 如果是相对路径，转换为绝对路径
            self.rss_media_path = os.path.abspath(self.rss_media_path)
        
        logger.info(f"RSS媒体文件存储路径: {self.rss_media_path}")
        
        # 确保媒体文件存储路径存在
        Path(self.rss_media_path).mkdir(parents=True, exist_ok=True)
    
    async def _process(self, context):
        """处理RSS过滤器逻辑"""
        if not context.should_forward:
            logger.info("消息被前置过滤器过滤，跳过RSS处理")
            return False
        
        # 执行RSS规则前，先确保媒体文件已经下载
        # 媒体组消息需要特殊处理
        if context.is_media_group:
            rule = context.rule
            if rule.enable_rss:
                await self._process_media_group(context, rule)
        else:
            # 获取消息和规则
            message = context.event.message
            client = context.client
            rule = context.rule
            
            # 检查规则是否启用RSS
            if rule.enable_rss:
                try:
                    # 准备条目数据
                    entry_data = await self._prepare_entry_data(client, message, rule, context)
                    
                    # 如果准备数据失败，记录错误并尝试生成简单的数据
                    if entry_data is None:
                        logger.warning("生成RSS条目数据失败，尝试创建简单数据")
                        # 尝试从消息中提取最基本的信息
                        message_text = getattr(message, 'text', '') or getattr(message, 'caption', '') or '文件消息'
                        entry_data = {
                            "id": str(message.id),
                            "title": message_text[:50] + ('...' if len(message_text) > 50 else ''),
                            "content": message_text,
                            "published": datetime.now().isoformat(),
                            "author": "",
                            "link": "",
                            "media": []
                        }
                        
                        # 如果消息有媒体，尝试处理
                        if hasattr(message, 'media') and message.media:
                            media_info = await self._process_media(client, message, context)
                            if media_info:
                                if isinstance(media_info, list):
                                    entry_data["media"].extend(media_info)
                                else:
                                    entry_data["media"].append(media_info)
                    
                    # 发送到RSS服务
                    if entry_data:
                        success = await self._send_to_rss_service(rule.id, entry_data)
                        if success:
                            logger.info(f"成功将消息添加到规则 {rule.id} 的RSS订阅源")
                        else:
                            logger.error(f"无法将消息添加到规则 {rule.id} 的RSS订阅源")
                    else:
                        logger.error("无法生成有效的RSS条目数据")
                
                except Exception as e:
                    logger.error(f"RSS处理时出错: {str(e)}")
        
        # RSS过滤器不阻止消息继续被处理
        return True
    
    async def _prepare_entry_data(self, client, message, rule, context=None):
        """准备RSS条目数据"""
        try:
            # 获取标题（使用自定义方法）
            title = self._get_message_title(message)
            
            # 安全获取消息内容
            content = ""
            if hasattr(message, 'text') and message.text:
                content = message.text
            elif hasattr(message, 'caption') and message.caption:
                content = message.caption
            
            # 获取发送人名称
            author = await self._get_sender_name(client, message)
            
            # 获取消息链接（如果有）
            link = self._get_message_link(message)
            
            # 获取媒体（如果有）
            media_list = []
            
            # 处理媒体组消息
            if context and hasattr(context, "is_media_group") and context.is_media_group:
                logger.debug("处理媒体组消息")
                # 由于媒体组已经在其他地方处理，这里不再重复处理
                # 仅记录
                logger.debug("媒体组在其他地方处理")
            else:
                # 处理单个消息的媒体
                media_info = await self._process_media(client, message, context)
                if media_info:
                    if isinstance(media_info, list):
                        media_list.extend(media_info)
                    else:
                        media_list.append(media_info)
                elif media_list:
                    logger.debug(f"_process_media返回了多个媒体: {len(media_list)}")
                
                # 尝试记录媒体信息
                if media_list:
                    for i, media in enumerate(media_list):
                        logger.debug(f"媒体{i+1}: {media.get('filename', 'unknown')}, 类型: {media.get('type', 'unknown')}, 原始文件名: {media.get('original_name', 'unknown')}")
            
            # 构建条目数据
            entry_data = {
                "id": str(message.id),
                "title": title,
                "content": content,
                "published": message.date.isoformat(),
                "author": author,
                "link": link,
                "media": media_list
            }
            
            return entry_data
            
        except Exception as e:
            logger.error(f"准备RSS条目数据时出错: {str(e)}")
            return None
    
    def _get_message_title(self, message):
        """获取消息标题"""
        # 使用消息的前20个字符作为标题
        text = ""
        if hasattr(message, 'text') and message.text:
            text = message.text
        elif hasattr(message, 'caption') and message.caption:
            text = message.caption
            
        title = text.split('\n')[0][:20].strip() if text else ""
        
        # 如果标题为空，使用默认标题
        if not title:
            # 检测各种媒体类型
            has_photo = hasattr(message, 'photo') and message.photo
            has_video = hasattr(message, 'video') and message.video
            has_document = hasattr(message, 'document') and message.document
            has_audio = hasattr(message, 'audio') and message.audio
            has_voice = hasattr(message, 'voice') and message.voice
            
            if has_photo:
                title = "图片消息"
            elif has_video:
                title = "视频消息"
            elif has_document:
                doc_name = ""
                if hasattr(message.document, 'file_name') and message.document.file_name:
                    doc_name = message.document.file_name
                title = f"文件: {doc_name}" if doc_name else "文件消息"
            elif has_audio:
                audio_name = ""
                if hasattr(message.audio, 'file_name') and message.audio.file_name:
                    audio_name = message.audio.file_name
                title = f"音频: {audio_name}" if audio_name else "音频消息"
            elif has_voice:
                title = "语音消息"
            else:
                title = "新消息"
        
        return title
    
    async def _get_sender_name(self, client, message):
        """获取发送者名称"""
        try:
            # 检查是否是频道消息
            if hasattr(message, 'sender_chat') and message.sender_chat:
                return message.sender_chat.title
            # 检查是否有发送者信息
            elif hasattr(message, 'from_user') and message.from_user:
                return message.from_user.first_name + (f" {message.from_user.last_name}" if message.from_user.last_name else "")
            # 尝试从聊天获取名称
            elif hasattr(message, 'chat') and message.chat:
                if hasattr(message.chat, 'title') and message.chat.title:
                    return message.chat.title
                elif hasattr(message.chat, 'first_name'):
                    return message.chat.first_name + (f" {message.chat.last_name}" if hasattr(message.chat, 'last_name') and message.chat.last_name else "")
            return "未知用户"
        except Exception as e:
            logger.error(f"获取发送者名称时出错: {str(e)}")
            return "未知用户"
    
    def _get_message_link(self, message):
        """获取消息链接"""
        try:
            if hasattr(message, 'chat') and message.chat:
                chat_id = getattr(message.chat, 'id', None)
                username = getattr(message.chat, 'username', None)
                message_id = getattr(message, 'id', None)
                
                if message_id is None:
                    return ""
                    
                if username:
                    return f"https://t.me/{username}/{message_id}"
                elif chat_id:
                    # 使用chat_id创建链接
                    chat_id_str = str(chat_id)
                    # 移除前导负号（如果有）
                    if chat_id_str.startswith('-100'):
                        chat_id_str = chat_id_str[4:]  # 去掉'-100'
                    elif chat_id_str.startswith('-'):
                        chat_id_str = chat_id_str[1:]  # 去掉'-'
                    return f"https://t.me/c/{chat_id_str}/{message_id}"
            return ""
        except Exception as e:
            logger.error(f"获取消息链接时出错: {str(e)}")
            return ""
    
    async def _process_media(self, client, message, context=None):
        """处理媒体内容"""
        media_list = []
        
        try:
            # 处理文档类型
            if hasattr(message, 'document') and message.document:
                # 获取原始文件名
                original_name = None
                for attr in message.document.attributes:
                    if hasattr(attr, 'file_name'):
                        original_name = attr.file_name
                        break
                
                # 生成文件名
                message_id = getattr(message, 'id', 'unknown')
                file_name = original_name if original_name else f"document_{message_id}"
                file_name = self._sanitize_filename(file_name)
                
                # 下载文件
                local_path = os.path.join(self.rss_media_path, file_name)
                try:
                    if not os.path.exists(local_path):
                        await message.download_media(local_path)
                        logger.info(f"下载媒体文件到: {local_path}")
                    
                    # 获取文件大小和MIME类型
                    file_size = os.path.getsize(local_path)
                    mime_type = message.document.mime_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
                    
                    # 添加到媒体列表
                    media_info = {
                        "url": f"/media/{file_name}",
                        "type": mime_type,
                        "size": file_size,
                        "filename": file_name,
                        "original_name": original_name or file_name
                    }
                    media_list.append(media_info)
                    logger.info(f"添加文档到RSS: {file_name}, 原始文件名: {original_name or '未知'}")
                except Exception as e:
                    logger.error(f"处理文档时出错: {str(e)}")
            
            # 处理图片类型
            elif hasattr(message, 'photo') and message.photo:
                message_id = getattr(message, 'id', 'unknown')
                file_name = f"photo_{message_id}.jpg"
                local_path = os.path.join(self.rss_media_path, file_name)
                
                try:
                    if not os.path.exists(local_path):
                        await message.download_media(local_path)
                        logger.info(f"下载图片到: {local_path}")
                    
                    # 获取文件大小
                    file_size = os.path.getsize(local_path)
                    
                    # 添加到媒体列表
                    media_info = {
                        "url": f"/media/{file_name}",
                        "type": "image/jpeg",
                        "size": file_size,
                        "filename": file_name,
                        "original_name": "photo.jpg"  # 图片类型没有原始文件名
                    }
                    media_list.append(media_info)
                    logger.info(f"添加图片到RSS: {file_name}")
                except Exception as e:
                    logger.error(f"处理图片时出错: {str(e)}")
            
            # 处理视频类型
            elif hasattr(message, 'video') and message.video:
                # 获取原始文件名
                original_name = None
                for attr in message.video.attributes:
                    if hasattr(attr, 'file_name'):
                        original_name = attr.file_name
                        break
                
                message_id = getattr(message, 'id', 'unknown')
                file_name = original_name if original_name else f"video_{message_id}.mp4"
                file_name = self._sanitize_filename(file_name)
                local_path = os.path.join(self.rss_media_path, file_name)
                
                try:
                    if not os.path.exists(local_path):
                        await message.download_media(local_path)
                        logger.info(f"下载视频到: {local_path}")
                    
                    # 获取文件大小
                    file_size = os.path.getsize(local_path)
                    
                    # 添加到媒体列表
                    media_info = {
                        "url": f"/media/{file_name}",
                        "type": "video/mp4",
                        "size": file_size,
                        "filename": file_name,
                        "original_name": original_name or file_name
                    }
                    media_list.append(media_info)
                    logger.info(f"添加视频到RSS: {file_name}, 原始文件名: {original_name or '未知'}")
                except Exception as e:
                    logger.error(f"处理视频时出错: {str(e)}")
            
            # 处理音频类型
            elif hasattr(message, 'audio') and message.audio:
                # 获取原始文件名
                original_name = None
                for attr in message.audio.attributes:
                    if hasattr(attr, 'file_name'):
                        original_name = attr.file_name
                        break
                
                message_id = getattr(message, 'id', 'unknown')
                file_name = original_name if original_name else f"audio_{message_id}.mp3"
                file_name = self._sanitize_filename(file_name)
                local_path = os.path.join(self.rss_media_path, file_name)
                
                try:
                    if not os.path.exists(local_path):
                        await message.download_media(local_path)
                        logger.info(f"下载音频到: {local_path}")
                    
                    # 获取文件大小
                    file_size = os.path.getsize(local_path)
                    
                    # 添加到媒体列表
                    media_info = {
                        "url": f"/media/{file_name}",
                        "type": "audio/mpeg",
                        "size": file_size,
                        "filename": file_name,
                        "original_name": original_name or file_name
                    }
                    media_list.append(media_info)
                    logger.info(f"添加音频到RSS: {file_name}, 原始文件名: {original_name or '未知'}")
                except Exception as e:
                    logger.error(f"处理音频时出错: {str(e)}")
            
            # 处理语音消息
            elif hasattr(message, 'voice') and message.voice:
                message_id = getattr(message, 'id', 'unknown')
                file_name = f"voice_{message_id}.ogg"
                local_path = os.path.join(self.rss_media_path, file_name)
                
                try:
                    if not os.path.exists(local_path):
                        await message.download_media(local_path)
                        logger.info(f"下载语音到: {local_path}")
                    
                    # 获取文件大小
                    file_size = os.path.getsize(local_path)
                    
                    # 添加到媒体列表
                    media_info = {
                        "url": f"/media/{file_name}",
                        "type": "audio/ogg",
                        "size": file_size,
                        "filename": file_name,
                        "original_name": "voice.ogg"  # 语音消息没有原始文件名
                    }
                    media_list.append(media_info)
                    logger.info(f"添加语音到RSS: {file_name}")
                except Exception as e:
                    logger.error(f"处理语音时出错: {str(e)}")
        
        except Exception as e:
            logger.error(f"处理媒体内容时出错: {str(e)}")
        
        return media_list
    
    def _sanitize_filename(self, filename):
        """处理文件名，去除不合法字符"""
        # 替换Windows和Unix系统不支持的文件名字符
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename
    
    async def _send_to_rss_service(self, rule_id, entry_data):
        """发送数据到RSS服务"""
        try:
            url = f"{self.rss_base_url}/api/entries/{rule_id}/add"
            
            # 记录要发送的数据（只记录非二进制数据）
            debug_data = entry_data.copy()
            if "media" in debug_data:
                media_files = []
                for media in debug_data["media"]:
                    if isinstance(media, dict):
                        original_name = media.get("original_name", "未知")
                        filename = media.get("filename", "未知")
                        media_files.append(f"{original_name}({filename})")
                    else:
                        media_files.append(str(media))
                debug_data["media"] = f"{len(debug_data['media'])} 个媒体文件: {', '.join(media_files)}"
            logger.info(f"发送到RSS服务: {url}, 数据: {debug_data}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=entry_data) as response:
                    response_text = await response.text()
                    if response.status != 200:
                        logger.error(f"发送到RSS服务失败: {response.status} - {response_text}")
                        return False
                    
                    logger.info(f"成功发送到RSS服务, 规则ID: {rule_id}, 响应: {response_text}")
                    return True
                    
        except Exception as e:
            logger.error(f"发送到RSS服务时出错: {str(e)}")
            return False
    
    async def _process_media_group(self, context, rule):
        """处理媒体组消息"""
        try:
            # 获取第一条消息作为基础消息
            base_message = context.event.message
            
            # 准备媒体列表
            media_list = []
            
            # 从context.media_files获取已下载的媒体文件
            # media_files由MediaFilter填充
            local_media_files = context.media_files if hasattr(context, 'media_files') else []
            
            # 记录调试信息
            logger.info(f"处理媒体组消息，已下载的媒体文件: {len(local_media_files)}")
            for file in local_media_files:
                logger.info(f"已下载媒体文件: {file}")
            
            # 如果没有已下载的媒体文件，尝试从media_group_messages直接获取
            if not local_media_files and context.media_group_messages:
                logger.warning("媒体组没有已下载的文件，尝试从media_group_messages获取")
                
                # 直接处理媒体组消息列表
                for idx, msg in enumerate(context.media_group_messages):
                    try:
                        # 尝试从消息中获取媒体信息
                        if hasattr(msg, 'photo') and msg.photo:
                            # 获取消息ID，用于生成默认文件名
                            message_id = getattr(msg, 'id', 'unknown')
                            file_name = f"photo_{message_id}.jpg"
                            file_name = self._sanitize_filename(file_name)
                            
                            # 直接下载媒体
                            try:
                                local_path = os.path.join(self.rss_media_path, file_name)
                                
                                # 如果文件已存在且大小正常，跳过下载
                                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                                    logger.info(f"媒体文件已存在，跳过下载: {local_path}")
                                else:
                                    # 尝试直接下载
                                    try:
                                        await msg.download_media(local_path)
                                        logger.info(f"直接下载媒体组图片到: {local_path}")
                                    except Exception as e:
                                        if "file reference has expired" in str(e):
                                            # 如果文件引用过期，尝试重新获取消息
                                            try:
                                                # 重新获取消息
                                                new_msg = await context.client.get_messages(
                                                    msg.chat_id,
                                                    ids=msg.id
                                                )
                                                if new_msg and new_msg.media:
                                                    await new_msg.download_media(local_path)
                                                    logger.info(f"通过重新获取消息下载媒体: {local_path}")
                                                else:
                                                    logger.error("无法重新获取消息或消息没有媒体")
                                                    continue
                                            except Exception as e2:
                                                logger.error(f"重新获取消息并下载失败: {str(e2)}")
                                                continue
                                        else:
                                            logger.error(f"下载媒体组图片时出错: {str(e)}")
                                            continue
                                
                                # 获取文件大小
                                if os.path.exists(local_path):
                                    file_size = os.path.getsize(local_path)
                                    
                                    # 添加到媒体列表
                                    media_info = {
                                        "url": f"/media/{file_name}",
                                        "type": "image/jpeg",
                                        "size": file_size,
                                        "filename": file_name,
                                        "original_name": "photo.jpg"  # 照片没有原始文件名
                                    }
                                    media_list.append(media_info)
                                    logger.info(f"添加媒体组图片到RSS: {file_name}")
                            except Exception as e:
                                logger.error(f"处理媒体组图片时出错: {str(e)}")
                        elif hasattr(msg, 'document') and msg.document:
                            # 获取消息ID，用于生成默认文件名
                            message_id = getattr(msg, 'id', 'unknown')
                            original_name = getattr(msg.document, 'file_name', None)
                            file_name = original_name if original_name else f"document_{message_id}"
                            file_name = self._sanitize_filename(file_name)
                            
                            try:
                                local_path = os.path.join(self.rss_media_path, file_name)
                                
                                # 如果文件已存在且大小正常，跳过下载
                                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                                    logger.info(f"媒体文件已存在，跳过下载: {local_path}")
                                else:
                                    try:
                                        await msg.download_media(local_path)
                                        logger.info(f"直接下载文档到: {local_path}")
                                    except Exception as e:
                                        if "file reference has expired" in str(e):
                                            try:
                                                new_msg = await context.client.get_messages(
                                                    msg.chat_id,
                                                    ids=msg.id
                                                )
                                                if new_msg and new_msg.media:
                                                    await new_msg.download_media(local_path)
                                                    logger.info(f"通过重新获取消息下载文档: {local_path}")
                                                else:
                                                    logger.error("无法重新获取消息或消息没有媒体")
                                                    continue
                                            except Exception as e2:
                                                logger.error(f"重新获取消息并下载失败: {str(e2)}")
                                                continue
                                        else:
                                            logger.error(f"下载文档时出错: {str(e)}")
                                            continue
                                
                                # 获取文件大小
                                if os.path.exists(local_path):
                                    file_size = os.path.getsize(local_path)
                                    media_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
                                    
                                    # 添加到媒体列表
                                    media_info = {
                                        "url": f"/media/{file_name}",
                                        "type": media_type,
                                        "size": file_size,
                                        "filename": file_name,
                                        "original_name": original_name
                                    }
                                    media_list.append(media_info)
                                    logger.info(f"添加文档到RSS: {file_name}")
                            except Exception as e:
                                logger.error(f"处理文档时出错: {str(e)}")
                        # 可以添加对其他媒体类型的支持（视频、音频等）
                    except Exception as e:
                        logger.error(f"处理媒体组消息 #{idx} 时出错: {str(e)}")
            else:
                # 使用已下载的媒体文件
                for local_file in local_media_files:
                    try:
                        # 从文件名猜测媒体类型
                        media_type = mimetypes.guess_type(local_file)[0] or "application/octet-stream"
                        filename = os.path.basename(local_file)
                        
                        # 复制文件到RSS媒体目录
                        target_path = os.path.join(self.rss_media_path, filename)
                        if not os.path.exists(target_path):
                            shutil.copy2(local_file, target_path)
                            logger.info(f"复制媒体文件到: {target_path}")
                        
                        # 获取文件大小
                        file_size = os.path.getsize(target_path)
                        
                        # 尝试从原始消息中获取文件名
                        original_name = None
                        for msg in context.media_group_messages:
                            if hasattr(msg, 'document') and msg.document:
                                original_name = getattr(msg.document, 'file_name', None)
                                if original_name:
                                    break
                        
                        # 添加到媒体列表
                        media_info = {
                            "url": f"/media/{filename}",
                            "type": media_type,
                            "size": file_size,
                            "filename": filename,
                            "original_name": original_name or filename
                        }
                        media_list.append(media_info)
                        logger.info(f"添加媒体组文件到RSS: {filename}, 原始文件名: {original_name or '未知'}")
                    except Exception as e:
                        logger.error(f"处理媒体组文件时出错: {str(e)}")
            
            # 准备条目数据
            now = datetime.now().isoformat()
            
            # 基本消息信息 - 使用第一条消息的信息
            message_text = ""
            if hasattr(base_message, 'text') and base_message.text:
                message_text = base_message.text
            elif hasattr(base_message, 'caption') and base_message.caption:
                message_text = base_message.caption
            
            # 构建标题
            title = message_text.split('\n')[0][:20].strip() if message_text else f"媒体组消息 ({len(context.media_group_messages)}张图片)"
            
            entry_data = {
                "id": str(base_message.id) if hasattr(base_message, 'id') else str(uuid.uuid4()),
                "rule_id": rule.id,
                "message_id": str(base_message.id) if hasattr(base_message, 'id') else "unknown",
                "title": title,
                "content": message_text,
                "published": now,
                "author": await self._get_sender_name(context.client, base_message),
                "link": self._get_message_link(base_message),
                "media": media_list  # 使用构建的媒体列表
            }
            
            # 记录调试信息
            logger.info(f"媒体组条目数据: 标题={title}, 媒体数量={len(media_list)}")
            
            # 发送到RSS服务
            if entry_data["media"]:
                await self._send_to_rss_service(rule.id, entry_data)
                logger.info(f"成功将媒体组消息添加到规则 {rule.id} 的RSS订阅源，共 {len(media_list)} 个媒体文件")
            else:
                logger.warning(f"媒体组消息没有有效的媒体文件，跳过添加到RSS订阅源")
        except Exception as e:
            logger.error(f"处理媒体组RSS消息时出错: {str(e)}")
            # 继续处理流程
