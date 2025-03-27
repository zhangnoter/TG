VERSION = "1.7"

# 版本号说明
VERSION_INFO = {
    "major": 1,        # 主版本号：重大更新，可能不兼容旧版本
    "feature": 7,      # 功能版本号：添加重要新功能
    "minor": 0,        # 次要版本号：添加小功能或优化
    "patch": 0,        # 补丁版本号：Bug修复和小改动
} 


UPDATE_INFO = """<blockquote><b>✨ 更新日志 v1.7</b>

- 集成Apprise，现已支持多种通知方式，不再局限于Telegram内转发

- 添加放行文本功能，开启后过滤媒体时不会整条消息屏蔽，而是单独转发文本

- 统一鉴权方法

- 调整过滤器顺序

</blockquote>
"""


WELCOME_TEXT = """
<b>🎉 欢迎使用 TelegramForwarder !</b>
        
如果您觉得这个项目对您有帮助，欢迎通过以下方式支持我:

<blockquote>⭐ <b>给项目点个小小的 Star:</b> <a href='https://github.com/Heavrnl/TelegramForwarder'>TelegramForwarder</a>
☕ <b>请我喝杯咖啡:</b> <a href='https://ko-fi.com/0heavrnl'>Ko-fi</a></blockquote>

当前版本: v1.7
更新日志: /changelog

感谢您的支持!
"""