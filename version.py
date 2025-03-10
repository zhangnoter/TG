VERSION = "1.5"

# 版本号说明
VERSION_INFO = {
    "major": 1,        # 主版本号：重大更新，可能不兼容旧版本
    "feature": 5,      # 功能版本号：添加重要新功能
    "minor": 0,        # 次要版本号：添加小功能或优化
    "patch": 0,        # 补丁版本号：Bug修复和小改动
} 


UPDATE_INFO = """<blockquote><b>✨ 更新日志 v1.5</b>

-  新增 RSS 订阅功能，前往Readme查看完成说明

- 增强 /settings 指令，可用/settings [规则ID] 直接打开规则设置页面

- 增强 /bind 指令，现在bind指令支持两个参数 /bind <源聊天链接或名称> [目标聊天链接或名称]

- 添加/delete_rss_user(/dru)指令，防止你忘记密码，可以直接删除用户而不删除数据，之后进入网页可重新创建用户

- 优化交互，给部分设置界面添加关闭按钮，直接删除消息

- 优化读取ai模型代码逻辑，请在 `config/ai_models.json` 添加你的自定义模型名字

- 添加自动删除消息功能，可在.env里配置


# bot消息删除时间 (秒),0表示立即删除, -1表示不删除
BOT_MESSAGE_DELETE_TIMEOUT=60

# 是否自动删除用户发送的指令消息 (true/false)
USER_MESSAGE_DELETE_ENABLE=true


- 修复过滤逻辑导致的编辑模式不起作用的问题

</blockquote>
"""


WELCOME_TEXT = """
<b>🎉 欢迎使用 TelegramForwarder !</b>
        
如果您觉得这个项目对您有帮助，欢迎通过以下方式支持我:

<blockquote>⭐ <b>给项目点个小小的 Star:</b> <a href='https://github.com/Heavrnl/TelegramForwarder'>TelegramForwarder</a>
☕ <b>请我喝杯咖啡:</b> <a href='https://ko-fi.com/0heavrnl'>Ko-fi</a></blockquote>

当前版本: v1.5
更新日志: /changelog

感谢您的支持!
"""