VERSION = "1.4.2"

# 版本号说明
VERSION_INFO = {
    "major": 1,        # 主版本号：重大更新，可能不兼容旧版本
    "feature": 4,      # 功能版本号：添加重要新功能
    "minor": 2,        # 次要版本号：添加小功能或优化
    "patch": 0,        # 补丁版本号：Bug修复和小改动
} 

# 数据库版本号，每次修改数据库结构时递增
DB_VERSION = 2

UPDATE_INFO = """

<blockquote><b>✨ 更新日志 v1.4.2</b>

- 增强AI提示词，支持获取源聊天和目标聊天的消息，在提示词中使用以下格式：

- {source_message_context:数字} - 获取源聊天窗口最新的指定数量消息
- {target_message_context:数字} - 获取目标聊天窗口最新的指定数量消息
- {source_message_time:数字} - 获取源聊天窗口最近指定分钟数的消息
- {target_message_time:数字} - 获取目标聊天窗口最近指定分钟数的消息

</blockquote>
"""