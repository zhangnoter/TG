from feedgen.feed import FeedGenerator
from datetime import datetime, timedelta
from ..core.config import settings

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