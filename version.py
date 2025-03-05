VERSION = "1.4.1"

# 版本号说明
VERSION_INFO = {
    "major": 1,        # 主版本号：重大更新，可能不兼容旧版本
    "feature": 4,      # 功能版本号：添加重要新功能
    "minor": 1,        # 次要版本号：添加小功能或优化
    "patch": 0,        # 补丁版本号：Bug修复和小改动
} 

# 数据库版本号，每次修改数据库结构时递增
DB_VERSION = 2

UPDATE_INFO = """

<blockquote><b>✨ 更新日志 v1.4.1</b>

- 添加 /list_rule （/lr）指令，可以列出所有转发规则

- 添加 /delete_rule （/dr）指令，可以删除指定转发规则

- 优化 /list_keyword 显示交互
</blockquote>
"""