"""
自定义异常类
"""

class ValidationError(Exception):
    """数据验证错误"""
    pass

class NotFoundError(Exception):
    """资源未找到错误"""
    pass

class DatabaseError(Exception):
    """数据库操作错误"""
    pass 