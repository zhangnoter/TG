from sqlalchemy.exc import IntegrityError
from handlers.models import Keyword, ReplaceRule
import logging

logger = logging.getLogger(__name__)

async def add_keywords(session, rule_id, keywords, is_regex=False):
    """添加关键字到规则
    
    Args:
        session: 数据库会话
        rule_id: 规则ID
        keywords: 关键字列表
        is_regex: 是否是正则表达式
        
    Returns:
        tuple: (成功数量, 重复数量)
    """
    success_count = 0
    duplicate_count = 0
    
    for keyword in keywords:
        try:
            new_keyword = Keyword(
                rule_id=rule_id,
                keyword=keyword,
                is_regex=is_regex
            )
            session.add(new_keyword)
            session.flush()
            success_count += 1
        except IntegrityError:
            session.rollback()
            duplicate_count += 1
            continue
            
    return success_count, duplicate_count

async def get_keywords(session, rule_id):
    """获取规则的所有关键字
    
    Args:
        session: 数据库会话
        rule_id: 规则ID
        
    Returns:
        list: 关键字列表
    """
    return session.query(Keyword).filter(
        Keyword.rule_id == rule_id
    ).all()

async def delete_keywords(session, rule_id, indices):
    """删除指定索引的关键字
    
    Args:
        session: 数据库会话
        rule_id: 规则ID
        indices: 要删除的索引列表（1-based）
        
    Returns:
        tuple: (删除数量, 剩余关键字列表)
    """
    keywords = await get_keywords(session, rule_id)
    if not keywords:
        return 0, []
        
    deleted_count = 0
    max_id = len(keywords)
    
    for idx in indices:
        if 1 <= idx <= max_id:
            keyword = keywords[idx - 1]
            session.delete(keyword)
            deleted_count += 1
            
    return deleted_count, await get_keywords(session, rule_id)

async def add_replace_rules(session, rule_id, patterns, contents=None):
    """添加替换规则
    
    Args:
        session: 数据库会话
        rule_id: 规则ID
        patterns: 匹配模式列表
        contents: 替换内容列表（可选）
        
    Returns:
        tuple: (成功数量, 重复数量)
    """
    success_count = 0
    duplicate_count = 0
    
    if contents is None:
        contents = [''] * len(patterns)
    
    for pattern, content in zip(patterns, contents):
        try:
            new_rule = ReplaceRule(
                rule_id=rule_id,
                pattern=pattern,
                content=content
            )
            session.add(new_rule)
            session.flush()
            success_count += 1
        except IntegrityError:
            session.rollback()
            duplicate_count += 1
            continue
            
    return success_count, duplicate_count

async def get_replace_rules(session, rule_id):
    """获取规则的所有替换规则
    
    Args:
        session: 数据库会话
        rule_id: 规则ID
        
    Returns:
        list: 替换规则列表
    """
    return session.query(ReplaceRule).filter(
        ReplaceRule.rule_id == rule_id
    ).all()

async def delete_replace_rules(session, rule_id, indices):
    """删除指定索引的替换规则
    
    Args:
        session: 数据库会话
        rule_id: 规则ID
        indices: 要删除的索引列表（1-based）
        
    Returns:
        tuple: (删除数量, 剩余替换规则列表)
    """
    rules = await get_replace_rules(session, rule_id)
    if not rules:
        return 0, []
        
    deleted_count = 0
    max_id = len(rules)
    
    for idx in indices:
        if 1 <= idx <= max_id:
            rule = rules[idx - 1]
            session.delete(rule)
            deleted_count += 1
            
    return deleted_count, await get_replace_rules(session, rule_id) 