from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Enum, UniqueConstraint, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from enums.enums import ForwardMode, PreviewMode, MessageMode, AddMode, HandleMode
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
    is_filter_user_info = Column(Boolean, default=False)  # 是否过滤用户信息
    handle_mode = Column(Enum(HandleMode), nullable=False, default=HandleMode.FORWARD) # 处理模式,编辑模式和转发模式，默认转发
    enable_comment_button = Column(Boolean, default=False)  # 是否添加对应消息的评论区直达按钮
    # AI相关字段
    is_ai = Column(Boolean, default=False)  # 是否启用AI处理
    ai_model = Column(String, nullable=True)  # 使用的AI模型
    ai_prompt = Column(String, nullable=True)  # AI处理的prompt
    is_summary = Column(Boolean, default=False)  # 是否启用AI总结
    summary_time = Column(String(5), default=os.getenv('DEFAULT_SUMMARY_TIME', '07:00'))
    summary_prompt = Column(String, nullable=True)  # AI总结的prompt
    is_keyword_after_ai = Column(Boolean, default=False) # AI处理后是否再次执行关键字过滤
    is_top_summary = Column(Boolean, default=True) # 是否顶置总结消息
    enable_delay = Column(Boolean, default=False)  # 是否启用延迟处理
    delay_seconds = Column(Integer, default=5)  # 延迟处理秒数
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
    """数据库迁移函数，确保新字段的添加"""
    inspector = inspect(engine)

    # 检查forward_rules表的现有列
    forward_rules_columns = {column['name'] for column in inspector.get_columns('forward_rules')}

    # 检查Keyword表的现有列
    keyword_columns = {column['name'] for column in inspector.get_columns('keywords')}

    # 需要添加的新列及其默认值
    forward_rules_new_columns = {
        'is_ai': 'ALTER TABLE forward_rules ADD COLUMN is_ai BOOLEAN DEFAULT FALSE',
        'ai_model': 'ALTER TABLE forward_rules ADD COLUMN ai_model VARCHAR DEFAULT NULL',
        'ai_prompt': 'ALTER TABLE forward_rules ADD COLUMN ai_prompt VARCHAR DEFAULT NULL',
        'is_summary': 'ALTER TABLE forward_rules ADD COLUMN is_summary BOOLEAN DEFAULT FALSE',
        'summary_time': 'ALTER TABLE forward_rules ADD COLUMN summary_time VARCHAR DEFAULT "07:00"',
        'summary_prompt': 'ALTER TABLE forward_rules ADD COLUMN summary_prompt VARCHAR DEFAULT NULL',
        'is_delete_original': 'ALTER TABLE forward_rules ADD COLUMN is_delete_original BOOLEAN DEFAULT FALSE',
        'is_original_sender': 'ALTER TABLE forward_rules ADD COLUMN is_original_sender BOOLEAN DEFAULT FALSE',
        'is_original_time': 'ALTER TABLE forward_rules ADD COLUMN is_original_time BOOLEAN DEFAULT FALSE',
        'is_keyword_after_ai': 'ALTER TABLE forward_rules ADD COLUMN is_keyword_after_ai BOOLEAN DEFAULT FALSE',
        'add_mode': 'ALTER TABLE forward_rules ADD COLUMN add_mode VARCHAR DEFAULT "BLACKLIST"',
        'enable_rule': 'ALTER TABLE forward_rules ADD COLUMN enable_rule BOOLEAN DEFAULT TRUE',
        'is_top_summary': 'ALTER TABLE forward_rules ADD COLUMN is_top_summary BOOLEAN DEFAULT TRUE',
        'is_filter_user_info': 'ALTER TABLE forward_rules ADD COLUMN is_filter_user_info BOOLEAN DEFAULT FALSE',
        'enable_delay': 'ALTER TABLE forward_rules ADD COLUMN enable_delay BOOLEAN DEFAULT FALSE',
        'delay_seconds': 'ALTER TABLE forward_rules ADD COLUMN delay_seconds INTEGER DEFAULT 5',
        'handle_mode': 'ALTER TABLE forward_rules ADD COLUMN handle_mode VARCHAR DEFAULT "FORWARD"',
        'enable_comment_button': 'ALTER TABLE forward_rules ADD COLUMN enable_comment_button BOOLEAN DEFAULT FALSE',
    }

    keywords_new_columns = {
        'is_blacklist': 'ALTER TABLE keywords ADD COLUMN is_blacklist BOOLEAN DEFAULT TRUE',
    }

    # 添加缺失的列
    with engine.connect() as connection:
        # 添加forward_rules表的列
        for column, sql in forward_rules_new_columns.items():
            if column not in forward_rules_columns:
                try:
                    connection.execute(text(sql))
                    logging.info(f'已添加列: {column}')
                except Exception as e:
                    logging.error(f'添加列 {column} 时出错: {str(e)}')
                    

        # 添加keywords表的列
        for column, sql in keywords_new_columns.items():
            if column not in keyword_columns:
                try:
                    connection.execute(text(sql))
                    logging.info(f'已添加列: {column}')
                except Exception as e:
                    logging.error(f'添加列 {column} 时出错: {str(e)}')

        #先检查forward_rules表的列的forward_mode是否存在
        if 'forward_mode' not in forward_rules_columns:
            # 修改forward_rules表的列mode为forward_mode
            connection.execute(text("ALTER TABLE forward_rules RENAME COLUMN mode TO forward_mode"))
            logging.info('修改forward_rules表的列mode为forward_mode成功')

        # 修改keywords表的唯一约束
        try:
            with engine.connect() as connection:
                # 检查索引是否存在
                result = connection.execute(text("""
                    SELECT name FROM sqlite_master 
                    WHERE type='index' AND name='unique_rule_keyword_is_regex_is_blacklist'
                """))
                index_exists = result.fetchone() is not None
                if not index_exists:
                    logging.info('开始更新 keywords 表的唯一约束...')
                    try:
                        
                        with engine.begin() as connection:
                            # 创建临时表
                            connection.execute(text("""
                                CREATE TABLE keywords_temp (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    rule_id INTEGER,
                                    keyword TEXT,
                                    is_regex BOOLEAN,
                                    is_blacklist BOOLEAN
                                    -- 如果 keywords 表还有其他字段，请在这里一并定义
                                )
                            """))
                            logging.info('创建 keywords_temp 表结构成功')

                            # 将原表数据复制到临时表，让数据库自动生成 id
                            result = connection.execute(text("""
                                INSERT INTO keywords_temp (rule_id, keyword, is_regex, is_blacklist)
                                SELECT rule_id, keyword, is_regex, is_blacklist FROM keywords
                            """))
                            logging.info(f'复制数据到 keywords_temp 成功，影响行数: {result.rowcount}')

                            # 删除原表 keywords
                            connection.execute(text("DROP TABLE keywords"))
                            logging.info('删除原表 keywords 成功')

                            # 4将临时表重命名为 keywords
                            connection.execute(text("ALTER TABLE keywords_temp RENAME TO keywords"))
                            logging.info('重命名 keywords_temp 为 keywords 成功')

                            # 添加唯一约束
                            connection.execute(text("""
                                CREATE UNIQUE INDEX unique_rule_keyword_is_regex_is_blacklist 
                                ON keywords (rule_id, keyword, is_regex, is_blacklist)
                            """))
                            logging.info('添加唯一约束 unique_rule_keyword_is_regex_is_blacklist 成功')

                            logging.info('成功更新 keywords 表结构和唯一约束')
                    except Exception as e:
                        logging.error(f'更新 keywords 表结构时出错: {str(e)}')
                else:
                    logging.info('唯一约束已存在，跳过创建')

        except Exception as e:
            logging.error(f'更新唯一约束时出错: {str(e)}')

def init_db():
    """初始化数据库"""
    engine = create_engine('sqlite:///./db/forward.db')

    # 首先创建所有表
    Base.metadata.create_all(engine)

    # 然后进行必要的迁移
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
    logging.info("数据库初始化和迁移完成。")