VERSION = "1.4.5"

# 版本号说明
VERSION_INFO = {
    "major": 1,        # 主版本号：重大更新，可能不兼容旧版本
    "feature": 4,      # 功能版本号：添加重要新功能
    "minor": 5,        # 次要版本号：添加小功能或优化
    "patch": 0,        # 补丁版本号：Bug修复和小改动
} 


UPDATE_INFO = """<blockquote><b>✨ 更新日志 v1.4.5</b>

  - 新增 /remove_all_keyword (简写: /rak) 命令
  - 可以通过关键词删除当前频道绑定的所有规则的关键字，如 "/rak \"hello world\" 'hello world'"

</blockquote>
"""