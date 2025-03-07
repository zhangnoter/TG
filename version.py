VERSION = "1.4.3"

# 版本号说明
VERSION_INFO = {
    "major": 1,        # 主版本号：重大更新，可能不兼容旧版本
    "feature": 4,      # 功能版本号：添加重要新功能
    "minor": 3,        # 次要版本号：添加小功能或优化
    "patch": 0,        # 补丁版本号：Bug修复和小改动
} 


UPDATE_INFO = """

<blockquote><b>✨ 更新日志 v1.4.3</b>

- 添加媒体扩展名过滤，可在 config/media_extensions.txt 中添加自定义扩展名

- （可选）请在 .env 中添加以下设置

# 媒体扩展名列表（行）
MEDIA_EXTENSIONS_ROWS=10
# 媒体扩展名列表（列）
MEDIA_EXTENSIONS_COLS=6

</blockquote>
"""