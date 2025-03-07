VERSION = "1.4.3.2"

# 版本号说明
VERSION_INFO = {
    "major": 1,        # 主版本号：重大更新，可能不兼容旧版本
    "feature": 4,      # 功能版本号：添加重要新功能
    "minor": 3,        # 次要版本号：添加小功能或优化
    "patch": 2,        # 补丁版本号：Bug修复和小改动
} 


UPDATE_INFO = """

<blockquote><b>✨ 更新日志 v1.4.3.2</b>

- 修复链接转发功能使用权限问题
- 增加每天凌晨3点自动更新chat表里的聊天信息

- （可选）在.env文件里设置以下环境变量

# 聊天信息更新时间 (24小时制)
CHAT_UPDATE_TIME=03:00

</blockquote>
"""