from feedgen.feed import FeedGenerator
from datetime import datetime, timedelta
from ..core.config import settings
from ..models.entry import Entry
from typing import List
import logging
import os
import base64
import mimetypes
from pathlib import Path

logger = logging.getLogger(__name__)

class FeedService:
    @staticmethod
    def generate_test_feed(rule_id: int) -> FeedGenerator:
        """生成测试 Feed"""
        fg = FeedGenerator()
        # 设置编码
        fg.load_extension('base', atom=True)
        fg.title(f'TG Forwarder RSS Test - Rule {rule_id}')
        fg.link(href='https://t.me/test_channel')
        fg.description('这是一个测试 RSS Feed')
        fg.language('zh-CN')
        
        # 获取当前时间（带时区）
        now = datetime.now(settings.DEFAULT_TIMEZONE)
        
        # 添加测试条目
        FeedService._add_text_entry(fg, now)
        FeedService._add_image_entry(fg, now)
        FeedService._add_link_entry(fg, now)
        FeedService._add_long_text_entry(fg, now)
        
        return fg
    
    @staticmethod
    async def generate_feed_from_entries(rule_id: int, entries: List[Entry]) -> FeedGenerator:
        """根据真实条目生成Feed"""
        fg = FeedGenerator()
        # 设置编码
        fg.load_extension('base', atom=True)
        
        # 获取第一个条目作为Feed标题和描述的来源
        if entries:
            first_entry = entries[0]
            # 尝试获取频道名作为Feed标题
            chat_name = FeedService._extract_chat_name(first_entry.link)
            fg.title(f'TG Forwarder - {chat_name or f"Rule {rule_id}"}')
            fg.description(f'TG Forwarder RSS - 规则 {rule_id} 的消息')
        else:
            fg.title(f'TG Forwarder RSS - Rule {rule_id}')
            fg.description('TG Forwarder RSS Feed')
        
        # 设置Feed链接
        base_url = f"http://{settings.HOST}:{settings.PORT}"
        fg.link(href=f'{base_url}/rss/{rule_id}')
        fg.language('zh-CN')
        
        # 添加条目
        for entry in entries:
            try:
                fe = fg.add_entry()
                fe.id(entry.id or entry.message_id)
                fe.title(entry.title)
                
                # 准备内容，包括可能的内嵌图片
                content = entry.content or ""
                
                # 添加图片 - 针对各种RSS阅读器的优化处理
                if entry.media:
                    # 检测是否为媒体组（多张图片）
                    is_media_group = len(entry.media) > 1
                    
                    # 处理每个媒体文件
                    for idx, media in enumerate(entry.media):
                        # 处理图片类型
                        if media.type.startswith('image/'):
                            try:
                                # 构建媒体文件路径
                                media_path = os.path.join(settings.MEDIA_PATH, media.filename)
                                if os.path.exists(media_path):
                                    # 标准的HTML图片标签
                                    img_url_tag = f'<p><img src="{base_url}{media.url}" alt="{media.filename}" style="max-width:100%;" /></p>'
                                    
                                    # 使用data URI方式（将图片直接编码到HTML中）
                                    try:
                                        # 检查文件大小，对大图片跳过base64编码
                                        file_size = os.path.getsize(media_path)
                                        # 仅对小于1MB的图片使用base64编码
                                        if file_size < 1024 * 1024:
                                            with open(media_path, "rb") as image_file:
                                                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                                                mime_type = media.type
                                                data_uri = f"data:{mime_type};base64,{encoded_string}"
                                                data_uri_tag = f'<p><img src="{data_uri}" alt="{media.filename}" style="max-width:100%;" /></p>'
                                                
                                                # 添加到内容
                                                if not content:
                                                    content = data_uri_tag
                                                else:
                                                    content += data_uri_tag
                                                    
                                                logger.info(f"已将图片作为base64编码到内容中: {media.filename}")
                                        else:
                                            # 对大图片使用URL方式
                                            logger.info(f"图片大小超过1MB，使用URL方式: {media.filename}")
                                            if not content:
                                                content = img_url_tag
                                            else:
                                                content += img_url_tag
                                    except Exception as e:
                                        # 如果base64编码失败，回退到URL方式
                                        if not content:
                                            content = img_url_tag
                                        else:
                                            content += img_url_tag
                                        logger.error(f"Base64编码图片失败，回退到URL方式: {str(e)}")
                            except Exception as e:
                                logger.error(f"内嵌图片时出错: {str(e)}")
                        elif media.type.startswith('video/'):
                            # 为视频添加特殊处理
                            display_name = ""
                            if hasattr(media, "original_name") and media.original_name:
                                display_name = media.original_name
                            else:
                                display_name = media.filename
                            video_tag = f'<p><a href="{base_url}{media.url}">下载视频 {display_name}</a></p>'
                            content += video_tag
                        elif media.type.startswith('audio/'):
                            # 为音频添加特殊处理
                            display_name = ""
                            if hasattr(media, "original_name") and media.original_name:
                                display_name = media.original_name
                            else:
                                display_name = media.filename
                            audio_tag = f'<p><a href="{base_url}{media.url}">下载音频 {display_name}</a></p>'
                            content += audio_tag
                        else:
                            # 其他类型文件添加下载链接
                            display_name = ""
                            if hasattr(media, "original_name") and media.original_name:
                                display_name = media.original_name
                            else:
                                display_name = media.filename
                            file_tag = f'<p><a href="{base_url}{media.url}">下载文件 {display_name}</a></p>'
                            content += file_tag
                
                # 设置内容和描述字段，确保两个字段都有图片和媒体内容
                # 这对于不同的RSS阅读器很重要，因为有些使用content，有些使用description
                if not content and entry.content:
                    content = entry.content
                
                # 确保content不为空，至少包含一些默认文本
                if not content:
                    content = "该消息没有文本内容。"
                    if entry.media and len(entry.media) > 0:
                        content += f" 包含 {len(entry.media)} 个媒体文件。"
                
                # 设置内容字段
                fe.content(content, type='html')
                
                # 确保description也包含同样的内容 - 有些阅读器依赖这个字段
                # 注意：使用pydantic模型的set方法
                for i, element in enumerate(fe._FeedEntry__atom_specificElements):
                    if element.get('name') == 'description':
                        fe._FeedEntry__atom_specificElements[i] = {'name': 'description', 'content': content}
                        break
                else:
                    # 如果没有找到description，添加一个
                    fe._FeedEntry__atom_specificElements.append({'name': 'description', 'content': content})
                
                # 解析ISO格式时间字符串，设置发布时间
                try:
                    published_dt = datetime.fromisoformat(entry.published)
                    fe.published(published_dt)
                except ValueError:
                    # 如果时间格式无效，使用当前时间
                    fe.published(datetime.now(settings.DEFAULT_TIMEZONE))
                
                # 设置作者和链接
                if entry.author:
                    fe.author(name=entry.author)
                
                if entry.link:
                    fe.link(href=entry.link)
                
                # 添加媒体附件
                if entry.media:
                    for media in entry.media:
                        try:
                            # 构建完整URL
                            media_url = f"{base_url}{media.url}"
                            # 确保长度为字符串
                            length = str(media.size) if hasattr(media, 'size') else "0"
                            # 添加enclosure，确保type字段存在
                            media_type = media.type if hasattr(media, 'type') else "application/octet-stream"
                            
                            # 记录添加的媒体附件
                            logger.info(f"添加媒体附件: {media_url}, 类型: {media_type}, 大小: {length}")
                            
                            # 添加enclosure
                            fe.enclosure(
                                url=media_url,
                                length=length,
                                type=media_type
                            )
                        except Exception as e:
                            logger.error(f"添加媒体附件时出错: {str(e)}")
            except Exception as e:
                logger.error(f"添加条目到Feed时出错: {str(e)}")
                continue
        
        return fg
    
    @staticmethod
    def _extract_chat_name(link: str) -> str:
        """从Telegram链接中提取频道/群组名称"""
        if not link or 't.me/' not in link:
            return ""
        
        try:
            # 例如从 https://t.me/channel_name/1234 提取 channel_name
            parts = link.split('t.me/')
            if len(parts) < 2:
                return ""
            
            channel_part = parts[1].split('/')[0]
            return channel_part
        except Exception:
            return ""
    
    @staticmethod
    def _add_text_entry(fg: FeedGenerator, now: datetime):
        entry = fg.add_entry()
        entry.id('1')
        entry.title('测试文本消息')
        entry.content('这是一条测试文本消息的内容', type='html')
        entry.published(now)
    
    @staticmethod
    def _add_image_entry(fg: FeedGenerator, now: datetime):
        entry = fg.add_entry()
        entry.id('2')
        entry.title('测试图片消息')
        entry.content('这是一条带图片的消息 <img src="https://picsum.photos/200/300" />', type='html')
        entry.published(now - timedelta(hours=1))
        entry.enclosure(
            url='https://picsum.photos/200/300',
            length='1024',
            type='image/jpeg'
        )
    
    @staticmethod
    def _add_link_entry(fg: FeedGenerator, now: datetime):
        entry = fg.add_entry()
        entry.id('3')
        entry.title('测试链接消息')
        entry.content('这是一条带链接的消息 <a href="https://example.com">示例链接</a>', type='html')
        entry.published(now - timedelta(hours=2))
    
    @staticmethod
    def _add_long_text_entry(fg: FeedGenerator, now: datetime):
        entry = fg.add_entry()
        entry.id('4')
        entry.title('测试长文本消息')
        entry.content('''
        这是一条很长的测试消息
        第二行内容
        第三行内容
        
        还可以包含一些格式：
        • 列表项 1
        • 列表项 2
        • 列表项 3
        
        甚至可以包含代码：
        ```python
        print("Hello, World!")
        ```
        ''', type='html')
        entry.published(now - timedelta(hours=3)) 