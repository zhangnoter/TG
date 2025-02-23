from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Enum, UniqueConstraint, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from enums.enums import ForwardMode, PreviewMode, MessageMode, AddMode
import logging
import os

Base = declarative_base()

class Chat(Base):
    __tablename__ = 'chats'

    id = Column(Integer, primary_key=True)
    telegram_chat_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    current_add_id = Column(String, nullable=True)

    # 关系
    source_rules = relationship('ForwardRule', foreign_keys='ForwardRule.source_chat_id', back_populates='source_chat')
    target_rules = relationship('ForwardRule', foreign_keys='ForwardRule.target_chat_id', back_populates='target_chat')

class ForwardRule(Base):
    __tablename__ = 'forward_rules'

    id = Column(Integer, primary_key=True)
    source_chat_id = Column(Integer, ForeignKey('chats.id'), nullable=False)
    target_chat_id = Column(Integer, ForeignKey('chats.id'), nullable=False)
    forward_mode = Column(Enum(ForwardMode), nullable=False, default=ForwardMode.BLACKLIST)
    use_bot = Column(Boolean, default=True)
    message_mode = Column(Enum(MessageMode), nullable=False, default=MessageMode.MARKDOWN)
    is_replace = Column(Boolean, default=False)
    is_preview = Column(Enum(PreviewMode), nullable=False, default=PreviewMode.FOLLOW)  # 三个值，开，关，按照原消息
    is_original_link = Column(Boolean, default=False)   # 是否附带原消息链接
    is_ufb = Column(Boolean, default=False)
    ufb_domain = Column(String, nullable=True)
    ufb_item = Column(String, nullable=True,default='main')
    is_delete_original = Column(Boolean, default=False)  # 是否删除原始消息
    is_original_sender = Column(Boolean, default=False)  # 是否附带原始消息发送人名称
    is_original_time = Column(Boolean, default=False)  # 是否附带原始消息发送时间
    add_mode = Column(Enum(AddMode), nullable=False, default=AddMode.BLACKLIST) # 添加模式,默认黑名单
    enable_rule = Column(Boolean, default=True)  # 是否启用规则
    # AI相关字段
    is_ai = Column(Boolean, default=False)  # 是否启用AI处理
    ai_model = Column(String, nullable=True)  # 使用的AI模型
    ai_prompt = Column(String, nullable=True)  # AI处理的prompt
    is_summary = Column(Boolean, default=False)  # 是否启用AI总结
    summary_time = Column(String(5), default=os.getenv('DEFAULT_SUMMARY_TIME', '07:00'))
    summary_prompt = Column(String, nullable=True)  # AI总结的prompt
    is_keyword_after_ai = Column(Boolean, default=False) # AI处理后是否再次执行关键字过滤
    is_top_summary = Column(Boolean, default=True) # 是否顶置总结消息
    # 添加唯一约束
    __table_args__ = (
        UniqueConstraint('source_chat_id', 'target_chat_id', name='unique_source_target'),
    )

    # 关系
    source_chat = relationship('Chat', foreign_keys=[source_chat_id], back_populates='source_rules')
    target_chat = relationship('Chat', foreign_keys=[target_chat_id], back_populates='target_rules')
    keywords = relationship('Keyword', back_populates='rule')
    replace_rules = relationship('ReplaceRule', back_populates='rule')


class Keyword(Base):
    __tablename__ = 'keywords'

    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey('forward_rules.id'), nullable=False)
    keyword = Column(String, nullable=True)
    is_regex = Column(Boolean, default=False)
    is_blacklist = Column(Boolean, default=True)

    # 关系
    rule = relationship('ForwardRule', back_populates='keywords')

    # 添加唯一约束
    __table_args__ = (
        UniqueConstraint('rule_id', 'keyword','is_regex','is_blacklist', name='unique_rule_keyword_is_regex_is_blacklist'),
    )

class ReplaceRule(Base):
    __tablename__ = 'replace_rules'

    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey('forward_rules.id'), nullable=False)
    pattern = Column(String, nullable=False)  # 替换模式
    content = Column(String, nullable=True)   # 替换内容

    # 关系
    rule = relationship('ForwardRule', back_populates='replace_rules')

    # 添加唯一约束
    __table_args__ = (
        UniqueConstraint('rule_id', 'pattern', 'content', name='unique_rule_pattern_content'),
    )

def migrate_db(engine):
    """数据库迁移函数，使用临时表迁移数据以回退到旧版本"""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    session = sessionmaker(bind=engine)()
    old_engine = create_engine('sqlite:///./db/forward.db') # 假设旧数据库也是同一个文件

    temp_table_names = {} # 用于存储临时表名

    with engine.connect() as connection:
        if 'chats' in table_names:
            temp_table_name = 'chats_temp_backup'
            temp_table_names['chats'] = temp_table_name
            logging.info(f"正在重命名 'chats' 表为 '{temp_table_name}'...")
            connection.execute(text(f"ALTER TABLE chats RENAME TO {temp_table_name}"))

        if 'forward_rules' in table_names:
            temp_table_name = 'forward_rules_temp_backup'
            temp_table_names['forward_rules'] = temp_table_name
            logging.info(f"正在重命名 'forward_rules' 表为 '{temp_table_name}'...")
            connection.execute(text(f"ALTER TABLE forward_rules RENAME TO {temp_table_name}"))

        if 'keywords' in table_names:
            temp_table_name = 'keywords_temp_backup'
            temp_table_names['keywords'] = temp_table_name
            logging.info(f"正在重命名 'keywords' 表为 '{temp_table_name}'...")
            connection.execute(text(f"ALTER TABLE keywords RENAME TO {temp_table_name}"))

        if 'replace_rules' in table_names:
            temp_table_name = 'replace_rules_temp_backup'
            temp_table_names['replace_rules'] = temp_table_name
            logging.info(f"正在重命名 'replace_rules' 表为 '{temp_table_name}'...")
            connection.execute(text(f"ALTER TABLE replace_rules RENAME TO {temp_table_name}"))

    logging.info("正在根据旧版模式创建表...")
    Base.metadata.create_all(engine) # 创建新表

    if 'chats' in temp_table_names:
        old_table_name = temp_table_names['chats']
        logging.info(f"正在迁移 'chats' 表数据，从 '{old_table_name}'...")
        with old_engine.connect() as old_connection:
            old_chats_result = old_connection.execute(text(f"SELECT id, telegram_chat_id, name, current_add_id FROM {old_table_name}"))
            for old_chat in old_chats_result:
                try:
                    new_chat = Chat(
                        id=old_chat.id,
                        telegram_chat_id=old_chat.telegram_chat_id,
                        name=old_chat.name,
                        current_add_id=old_chat.current_add_id,
                    )
                    session.add(new_chat)
                except Exception as e:
                    logging.error(f"迁移 chat id {old_chat.id} 时出错: {e}")
        logging.info("'chats' 表数据迁移完成。")

    if 'forward_rules' in temp_table_names:
        old_table_name = temp_table_names['forward_rules']
        logging.info(f"正在迁移 'forward_rules' 表数据，从 '{old_table_name}'...")
        with old_engine.connect() as old_connection:
            old_rules_result = old_connection.execute(text(f"""
                SELECT id, source_chat_id, target_chat_id, forward_mode, use_bot, message_mode,
                       is_replace, is_preview, is_original_link, is_ufb, ufb_domain, ufb_item,
                       is_delete_original, is_original_sender, is_original_time, add_mode, enable_rule,
                       is_ai, ai_model, ai_prompt, is_summary, summary_time, summary_prompt,
                       is_keyword_after_ai, is_top_summary
                FROM {old_table_name}
            """))
            for old_rule in old_rules_result:
                try:
                    new_rule = ForwardRule(
                        id=old_rule.id,
                        source_chat_id=old_rule.source_chat_id,
                        target_chat_id=old_rule.target_chat_id,
                        forward_mode=old_rule.forward_mode,
                        use_bot=old_rule.use_bot,
                        message_mode=old_rule.message_mode,
                        is_replace=old_rule.is_replace,
                        is_preview=old_rule.is_preview,
                        is_original_link=old_rule.is_original_link,
                        is_ufb=old_rule.is_ufb,
                        ufb_domain=old_rule.ufb_domain,
                        ufb_item=old_rule.ufb_item,
                        is_delete_original=old_rule.is_delete_original,
                        is_original_sender=old_rule.is_original_sender,
                        is_original_time=old_rule.is_original_time,
                        add_mode=old_rule.add_mode,
                        enable_rule=old_rule.enable_rule,
                        is_ai=old_rule.is_ai,
                        ai_model=old_rule.ai_model,
                        ai_prompt=old_rule.ai_prompt,
                        is_summary=old_rule.is_summary,
                        summary_time=old_rule.summary_time,
                        summary_prompt=old_rule.summary_prompt,
                        is_keyword_after_ai=old_rule.is_keyword_after_ai,
                        is_top_summary=old_rule.is_top_summary,
                    )
                    session.add(new_rule)
                except Exception as e:
                    logging.error(f"迁移 forward_rule id {old_rule.id} 时出错: {e}")
        logging.info("'forward_rules' 表数据迁移完成。")

    if 'keywords' in temp_table_names:
        old_table_name = temp_table_names['keywords']
        logging.info(f"正在迁移 'keywords' 表数据，从 '{old_table_name}'...")
        with old_engine.connect() as old_connection:
            old_keywords_result = old_connection.execute(text(f"SELECT id, rule_id, keyword, is_regex, is_blacklist FROM {old_table_name}"))
            for old_keyword in old_keywords_result:
                try:
                    new_keyword = Keyword(
                        id=old_keyword.id,
                        rule_id=old_keyword.rule_id,
                        keyword=old_keyword.keyword,
                        is_regex=old_keyword.is_regex,
                        is_blacklist=old_keyword.is_blacklist,
                    )
                    session.add(new_keyword)
                except Exception as e:
                    logging.error(f"迁移 keyword id {old_keyword.id} 时出错: {e}")
        logging.info("'keywords' 表数据迁移完成。")

    if 'replace_rules' in temp_table_names:
        old_table_name = temp_table_names['replace_rules']
        logging.info(f"正在迁移 'replace_rules' 表数据，从 '{old_table_name}'...")
        with old_engine.connect() as old_connection:
            old_replace_rules_result = old_connection.execute(text(f"SELECT id, rule_id, pattern, content FROM {old_table_name}"))
            for old_replace_rule in old_replace_rules_result:
                try:
                    new_replace_rule = ReplaceRule(
                        id=old_replace_rule.id,
                        rule_id=old_replace_rule.rule_id,
                        pattern=old_replace_rule.pattern,
                        content=old_replace_rule.content,
                    )
                    session.add(new_replace_rule)
                except Exception as e:
                    logging.error(f"迁移 replace_rule id {old_replace_rule.id} 时出错: {e}")
        logging.info("'replace_rules' 表数据迁移完成。")

    try:
        session.commit()
        logging.info("数据迁移事务提交成功。")
    except Exception as e:
        session.rollback()
        logging.error(f"提交数据迁移时出错: {e}")
    finally:
        session.close()

    with engine.connect() as connection:
        for original_table_name, temp_table_name in temp_table_names.items():
            logging.info(f"正在删除临时表 '{temp_table_name}'...")
            connection.execute(text(f"DROP TABLE {temp_table_name}"))
        logging.info("临时表删除完成。")

    logging.info("数据库迁移过程完成。")
    logging.info("请务必验证表之间的数据关系是否正确保留，例如 ForwardRule 中的 source_chat_id 和 target_chat_id 是否仍然指向有效的 Chat 记录，以及 Keyword 和 ReplaceRule 中的 rule_id 是否仍然指向有效的 ForwardRule 记录。")


def init_db():
    """初始化数据库"""
    engine = create_engine('sqlite:///./db/forward.db')

    # 执行迁移函数来重建表和迁移数据
    migrate_db(engine)

    return engine

def get_session():
    """创建会话工厂"""
    engine = create_engine('sqlite:///./db/forward.db')
    Session = sessionmaker(bind=engine)
    return Session()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    engine = init_db()
    session = get_session()
    logging.info("数据库初始化和迁移完成 (回退到旧版本，使用临时表).")