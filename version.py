VERSION = "1.4.4"

# 版本号说明
VERSION_INFO = {
    "major": 1,        # 主版本号：重大更新，可能不兼容旧版本
    "feature": 4,      # 功能版本号：添加重要新功能
    "minor": 4,        # 次要版本号：添加小功能或优化
    "patch": 0,        # 补丁版本号：Bug修复和小改动
} 


UPDATE_INFO = """<blockquote><b>✨ 更新日志 v1.4.4</b>

• 改进了带引号关键字的处理
  - 修复了 /add 和 /remove_keyword 命令对带空格关键字的处理问题
  - 现在可以正确添加和删除包含空格的关键字，如 "/add \"hello world\""

• 新增按ID删除关键字功能
  - 新增 /remove_keyword_by_id (简写: /rkbi) 命令
  - 可以通过序号删除关键字，如 "/rkbi 1 2 3"

</blockquote>
"""