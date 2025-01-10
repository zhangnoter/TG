import enum

class ForwardMode(enum.Enum):
    WHITELIST = 'whitelist'
    BLACKLIST = 'blacklist'

class PreviewMode(enum.Enum):
    ON = 'on'
    OFF = 'off'
    FOLLOW = 'follow'  # 跟随原消息的预览设置

class MessageMode(enum.Enum):
    MARKDOWN = 'Markdown'
    HTML = 'HTML' 