VERSION = "1.4.6"

# 版本号说明
VERSION_INFO = {
    "major": 1,        # 主版本号：重大更新，可能不兼容旧版本
    "feature": 4,      # 功能版本号：添加重要新功能
    "minor": 6,        # 次要版本号：添加小功能或优化
    "patch": 0,        # 补丁版本号：Bug修复和小改动
} 


UPDATE_INFO = """<blockquote><b>✨ 更新日志 v1.4.6</b>

  - 允许配置 Gemini 使用第三方 OpenAI 兼容接口
  - 允许配置 Claude 使用第三方接口

  请在 .env 文件中配置以下内容：
  GEMINI_API_BASE=
  CLAUDE_API_BASE=

</blockquote>
"""