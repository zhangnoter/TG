from sqlalchemy.exc import IntegrityError
from models.models import Keyword, ReplaceRule, ForwardRule
import logging
import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from ufb.ufb_client import UFBClient
from models.models import get_session

logger = logging.getLogger(__name__)
load_dotenv()



class DBOperations:
    def __init__(self):
        self.ufb_client = None

    @classmethod
    async def create(cls):
        """创建DBOperations实例"""
        instance = cls()
        await instance.init_ufb()
        return instance

    async def init_ufb(self):
        """初始化UFB客户端"""
        try:
            # 从环境变量获取UFB配置
            logger.info("初始化UFB客户端")
            is_ufb = os.getenv('UFB_ENABLED', 'false').lower() == 'true'
            if is_ufb:
                server_url = os.getenv('UFB_SERVER_URL', '')
                token = os.getenv('UFB_TOKEN')
                logger.info(f"UFB配置: server_url={server_url}, token={token and '***'}")
                
                if server_url and token:
                    # 处理URL
                    if not server_url.startswith(('ws://', 'wss://')):
                        if server_url.startswith('http://'):
                            server_url = f"ws://{server_url[7:]}"
                        elif server_url.startswith('https://'):
                            server_url = f"wss://{server_url[8:]}"
                        else:
                            server_url = f"wss://{server_url}"
                    
                    logger.info(f"处理后的URL: {server_url}")
                    self.ufb_client = UFBClient()
                    logger.info("UFB客户端已创建")
                    
                    try:
                        await self.ufb_client.start(server_url=server_url, token=token)
                        logger.info("UFB客户端已启动")
                    except Exception as e:
                        logger.error(f"UFB客户端启动失败: {str(e)}")
                        self.ufb_client = None
                else:
                    logger.warning("UFB配置不完整，未启用UFB功能")
                    self.ufb_client = None
            else:
                logger.info("UFB未启用")
        except Exception as e:
            logger.error(f"初始化UFB时出错: {str(e)}")
            self.ufb_client = None
    
    
    async def sync_to_server(self,session,rule_id):
        """同步UFB配置"""
        if self.ufb_client and os.getenv('UFB_ENABLED').lower() == 'true':
            # 通过rule_id获取规则ufb是否开启
            rule = session.query(ForwardRule).filter(ForwardRule.id == rule_id).first()
            ufb_domain = rule.ufb_domain
            if rule.is_ufb and ufb_domain:
                item = rule.ufb_item
                # 获取规则的所有非正则表达关键字
                normal_keywords = session.query(Keyword).filter(
                    Keyword.rule_id == rule_id,
                    Keyword.is_regex == False
                ).all()
                
                # 获取规则的所有正则表达关键字
                regex_keywords = session.query(Keyword).filter(
                    Keyword.rule_id == rule_id,
                    Keyword.is_regex == True
                ).all()

                # 获取../ufb/config/config.json文件
                config_file = Path(__file__).parent.parent / 'ufb' / 'config' / 'config.json'
                # 读取文件
                with open(config_file, 'r', encoding='utf-8') as file:
                    config = json.load(file)

                # 在userConfig中找到对应domain的配置
                for user_config in config.get('userConfig', []):
                    if user_config.get('domain') == ufb_domain:
                        # 根据item类型更新关键字
                        if item == 'main':
                            keywords_config = user_config.get('mainAndSubPageKeywords', {})
                        elif item == 'content':
                            keywords_config = user_config.get('contentPageKeywords', {})
                        elif item == 'main_username':
                            keywords_config = user_config.get('mainAndSubPageUserKeywords', {})
                        elif item == 'content_username':
                            keywords_config = user_config.get('contentPageUserKeywords', {})

                        # 更新关键字列表
                        keywords_config['keywords'] = [k.keyword for k in normal_keywords]
                        keywords_config['regexPatterns'] = [k.keyword for k in regex_keywords]

                        # 保存回对应的位置
                        if item == 'main':  
                            user_config['mainAndSubPageKeywords'] = keywords_config
                        elif item == 'content':
                            user_config['contentPageKeywords'] = keywords_config
                        elif item == 'main_username':
                            user_config['mainAndSubPageUserKeywords'] = keywords_config
                        elif item == 'content_username':
                            user_config['contentPageUserKeywords'] = keywords_config
                        else:
                            logger.error(f"未设置UFB_ITEM环境变量")
                            return
                        break
                
                # 更新时间戳
                config['globalConfig']['SYNC_CONFIG']['lastSyncTime'] = int(time.time() * 1000)
                # 保存到本地文件
                with open(config_file, 'w', encoding='utf-8') as file:
                    json.dump(config, file, ensure_ascii=False, indent=2)

                # 更新配置到服务器
                if self.ufb_client.is_connected:
                    await self.ufb_client.websocket.send(json.dumps({
                        "additional_info": "to_server",
                        "type": "update",
                        **config
                    }))
                    logger.info("UFB配置已同步")
                else:
                    logger.warning("UFB客户端未连接，无法同步配置")
            else:
                logger.warning("UFB未开启，无法同步配置")
        else:
            logger.warning("UFB客户端未初始化，无法同步配置")

    async def sync_from_json(self, config):
        """从收到的JSON配置同步关键字到数据库
        
        Args:
            config: 收到的配置数据
        """
        logger.info(f"从JSON同步关键字到数据库")
        session = get_session()
        try:
            # 获取所有启用了UFB的规则
            ufb_rules = session.query(ForwardRule).filter(
                ForwardRule.is_ufb == True,
                ForwardRule.ufb_domain != None
            ).all()
            
            if not ufb_rules:
                logger.info("没有找到启用UFB的规则")
                return
            logger.info(f"ufb_rules: {ufb_rules}")
            
            # 遍历所有启用UFB的规则
            for rule in ufb_rules:
                # 获取item类型
                item = rule.ufb_item
                logger.info(f"item: {item}")
                if not item:
                    logger.error("未设置UFB_ITEM环境变量")
                    continue  # 跳过没有设置 item 的规则
                
                # 在收到的配置中查找对应domain的配置
                for user_config in config.get('userConfig', []):
                    if user_config.get('domain') == rule.ufb_domain:
                        logger.info(f"找到匹配的domain配置: {rule.ufb_domain}")
                        
                        # 根据item类型获取关键字配置
                        if item == 'main':
                            keywords_config = user_config.get('mainAndSubPageKeywords', {})
                        elif item == 'content':
                            keywords_config = user_config.get('contentPageKeywords', {})
                        elif item == 'main_username':
                            keywords_config = user_config.get('mainAndSubPageUserKeywords', {})
                        elif item == 'content_username':
                            keywords_config = user_config.get('contentPageUserKeywords', {})
                        else:
                            logger.error(f"未设置UFB_ITEM环境变量")
                            continue
                        
                        # 清空现有关键字
                        session.query(Keyword).filter(
                            Keyword.rule_id == rule.id
                        ).delete()
                        
                        # 添加普通关键字
                        for keyword in keywords_config.get('keywords', []):
                            new_keyword = Keyword(
                                rule_id=rule.id,
                                keyword=keyword,
                                is_regex=False
                            )
                            session.add(new_keyword)
                            
                        # 添加正则关键字
                        for pattern in keywords_config.get('regexPatterns', []):
                            new_keyword = Keyword(
                                rule_id=rule.id,
                                keyword=pattern,
                                is_regex=True
                            )
                            session.add(new_keyword)
                        
                        session.commit()
                        logger.info(f"已从JSON同步关键字到规则 {rule.id} (domain: {rule.ufb_domain})")
                        break  # 找到匹配的domain后跳出内层循环
        finally:
            session.close()

    async def add_keywords(self, session, rule_id, keywords, is_regex=False):
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
                
        await self.sync_to_server(session, rule_id)
        return success_count, duplicate_count

    async def get_keywords(self, session, rule_id):
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

    async def delete_keywords(self, session, rule_id, indices):
        """删除指定索引的关键字
        
        Args:
            session: 数据库会话
            rule_id: 规则ID
            indices: 要删除的索引列表（1-based）
            
        Returns:
            tuple: (删除数量, 剩余关键字列表)
        """
        keywords = await self.get_keywords(session, rule_id)
        if not keywords:
            return 0, []
            
        deleted_count = 0
        max_id = len(keywords)
        
        for idx in indices:
            if 1 <= idx <= max_id:
                keyword = keywords[idx - 1]
                session.delete(keyword)
                deleted_count += 1

        await self.sync_to_server(session, rule_id)
        return deleted_count, await self.get_keywords(session, rule_id)

    async def add_replace_rules(self, session, rule_id, patterns, contents=None):
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

    async def get_replace_rules(self, session, rule_id):
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

    async def delete_replace_rules(self, session, rule_id, indices):
        """删除指定索引的替换规则
        
        Args:
            session: 数据库会话
            rule_id: 规则ID
            indices: 要删除的索引列表（1-based）
            
        Returns:
            tuple: (删除数量, 剩余替换规则列表)
        """
        rules = await self.get_replace_rules(session, rule_id)
        if not rules:
            return 0, []
            
        deleted_count = 0
        max_id = len(rules)
        
        for idx in indices:
            if 1 <= idx <= max_id:
                rule = rules[idx - 1]
                session.delete(rule)
                deleted_count += 1
                
        return deleted_count, await self.get_replace_rules(session, rule_id) 

