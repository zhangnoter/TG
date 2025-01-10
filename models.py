from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import enum

Base = declarative_base()

class ForwardMode(enum.Enum):
    WHITELIST = 'whitelist'
    BLACKLIST = 'blacklist'

class Chat(Base):
    __tablename__ = 'chats'
    
    id = Column(Integer, primary_key=True)
    telegram_chat_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    current_add_id = Column(String, nullable=True)  # 添加这个字段，存储当前选中的源聊天ID
    
    # 关系
    source_rules = relationship('ForwardRule', foreign_keys='ForwardRule.source_chat_id', back_populates='source_chat')
    target_rules = relationship('ForwardRule', foreign_keys='ForwardRule.target_chat_id', back_populates='target_chat')

class ForwardRule(Base):
    __tablename__ = 'forward_rules'
    
    id = Column(Integer, primary_key=True)
    source_chat_id = Column(Integer, ForeignKey('chats.id'), nullable=False)
    target_chat_id = Column(Integer, ForeignKey('chats.id'), nullable=False)
    mode = Column(Enum(ForwardMode), nullable=False, default=ForwardMode.BLACKLIST)
    use_bot = Column(Boolean, default=False)
    is_replace = Column(Boolean, default=False)
    #替换规则
    replace_rule = Column(String, nullable=True)
    #替换内容
    replace_content = Column(String, nullable=True)
    # 关系
    source_chat = relationship('Chat', foreign_keys=[source_chat_id], back_populates='source_rules')
    target_chat = relationship('Chat', foreign_keys=[target_chat_id], back_populates='target_rules')
    keywords = relationship('Keyword', back_populates='rule')

class Keyword(Base):
    __tablename__ = 'keywords'
    
    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey('forward_rules.id'), nullable=False)
    keyword = Column(String, nullable=True)
    is_regex = Column(Boolean, default=False)

    # 关系
    rule = relationship('ForwardRule', back_populates='keywords')

def migrate_db():
    """更新数据库结构"""
    engine = create_engine('sqlite:///forward.db')
    connection = engine.connect()
    
    try:
        # 检查并添加新的列
        connection.execute("""
            ALTER TABLE forward_rules 
            ADD COLUMN is_replace BOOLEAN DEFAULT FALSE
        """)
    except Exception:
        # 列已存在，忽略错误
        pass
        
    try:
        connection.execute("""
            ALTER TABLE forward_rules 
            ADD COLUMN replace_rule VARCHAR
        """)
    except Exception:
        pass
        
    try:
        connection.execute("""
            ALTER TABLE forward_rules 
            ADD COLUMN replace_content VARCHAR
        """)
    except Exception:
        pass
        
    connection.close()

def init_db():
    """初始化数据库"""
    engine = create_engine('sqlite:///forward.db')
    Base.metadata.create_all(engine)
    migrate_db()  # 运行迁移
    return engine

# 创建会话工厂
def get_session():
    engine = create_engine('sqlite:///forward.db')
    Session = sessionmaker(bind=engine)
    return Session() 