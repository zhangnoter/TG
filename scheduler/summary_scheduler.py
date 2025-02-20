import asyncio
from datetime import datetime, timedelta
import pytz
from models.models import get_session, ForwardRule
import logging
import os
from dotenv import load_dotenv
from telethon import TelegramClient
from ai import get_ai_provider
import traceback

logger = logging.getLogger(__name__)

class SummaryScheduler:
    def __init__(self, user_client: TelegramClient, bot_client: TelegramClient):
        self.tasks = {}  # 存储所有定时任务 {rule_id: task}
        self.timezone = pytz.timezone(os.getenv('DEFAULT_TIMEZONE', 'Asia/Shanghai'))
        self.user_client = user_client
        self.bot_client = bot_client
        
    async def schedule_rule(self, rule):
        """为规则创建或更新定时任务"""
        try:
            # 如果规则已有任务，先取消
            if rule.id in self.tasks:
                old_task = self.tasks[rule.id]
                old_task.cancel()
                logger.info(f"已取消规则 {rule.id} 的旧任务")
                del self.tasks[rule.id]
                
            # 如果启用了AI总结，创建新任务
            if rule.is_summary:
                # 计算下一次执行时间
                now = datetime.now(self.timezone)
                next_time = self._get_next_run_time(now, rule.summary_time)
                wait_seconds = (next_time - now).total_seconds()
                
                logger.info(f"规则 {rule.id} 的下一次执行时间: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"等待时间: {wait_seconds:.2f} 秒")
                
                task = asyncio.create_task(self._run_summary_task(rule))
                self.tasks[rule.id] = task
                logger.info(f"已为规则 {rule.id} 创建新的总结任务，时间: {rule.summary_time}")
            else:
                logger.info(f"规则 {rule.id} 的总结功能已关闭，不创建新任务")
                
        except Exception as e:
            logger.error(f"调度规则 {rule.id} 时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
        
    async def _run_summary_task(self, rule):
        """运行单个规则的总结任务"""
        while True:
            try:
                # 计算下一次执行时间
                now = datetime.now(self.timezone)
                target_time = self._get_next_run_time(now, rule.summary_time)
                
                # 等待到执行时间
                wait_seconds = (target_time - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                # 执行总结任务
                await self._execute_summary(rule)
                
            except asyncio.CancelledError:
                logger.info(f"规则 {rule.id} 的旧任务已取消")
                break
            except Exception as e:
                logger.error(f"规则 {rule.id} 的总结任务出错: {str(e)}")
                await asyncio.sleep(60)  # 出错后等待一分钟再重试
                
    def _get_next_run_time(self, now, target_time):
        """计算下一次运行时间"""
        hour, minute = map(int, target_time.split(':'))
        next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if next_time <= now:
            next_time += timedelta(days=1)
            
        return next_time
        
    async def _execute_summary(self, rule):
        """执行总结任务"""
        try:
            # 获取源聊天和目标聊天
            source_chat_id = int(rule.source_chat.telegram_chat_id)
            target_chat_id = int(rule.target_chat.telegram_chat_id)
            
            # 计算时间范围（从上次执行到现在）
            now = datetime.now(self.timezone)
            yesterday = now - timedelta(days=1)
            
            # 获取消息
            messages = []
            logger.info(f"\n开始获取 {rule.source_chat.name} 的消息...")
            
            async for message in self.user_client.iter_messages(
                source_chat_id,
                offset_date=yesterday,
                reverse=True
            ):
                if message.text:
                    # 获取发送时间
                    shanghai_time = message.date.astimezone(self.timezone)
                    formatted_time = shanghai_time.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 获取发送者信息
                    if message.sender:
                        sender_name = (
                            message.sender.title if hasattr(message.sender, 'title')
                            else f"{message.sender.first_name or ''} {message.sender.last_name or ''}".strip()
                        )
                    else:
                        sender_name = "Unknown"
                    
                    # 组合消息
                    formatted_message = f"[{formatted_time}] {sender_name}:\n{message.text}"
                    messages.append(formatted_message)
                    
                    # 日志输出
                    logger.info(f"\n发送时间: {formatted_time}")
                    logger.info(f"发送者: {sender_name}")
                    logger.info(f"消息内容: {formatted_message[:50]}")
            
            logger.info(f"\n共获取到 {len(messages)} 条消息")
            
            if not messages:
                logger.info(f"规则 {rule.id} 没有需要总结的消息")
                return
                
            # 准备AI总结
            all_messages = "\n".join(messages)
            
            # 获取数据库里的ai总结提示词
            prompt = rule.summary_prompt or os.getenv('DEFAULT_SUMMARY_PROMPT')
            
            # 如果提示词中有 {Messages} 占位符,替换为实际消息
            if prompt and '{Messages}' in prompt:
                prompt = prompt.replace('{Messages}', '\n'.join(messages))
                logger.info(f"处理后的总结提示词: {prompt}")

            logger.info("\n开始生成AI总结...")
            
            # 获取AI提供者
            ai_provider = get_ai_provider(rule.ai_model)
            await ai_provider.initialize()
            
            # 生成总结
            summary = await ai_provider.process_message(all_messages, prompt=prompt)
            
            if not summary:
                logger.error(f"规则 {rule.id} 生成总结失败")
                return
                
            logger.info("\nAI总结内容:")
            logger.info("=" * 50)
            logger.info(summary)
            logger.info("=" * 50)
            
            # 发送总结到目标聊天
            message_text = f"📋 {rule.source_chat.name} 24小时消息总结：\n\n{summary}"
            
            # 使用机器人发送
            await self.bot_client.send_message(
                target_chat_id,  # 直接使用 ID
                message_text,
                link_preview=False
            )
            
            logger.info(f"\n总结已发送到目标聊天: {rule.target_chat.name}")
            logger.info(f"规则 {rule.id} 的总结任务执行完成")
            
        except Exception as e:
            logger.error(f"执行规则 {rule.id} 的总结任务时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            
    async def start(self):
        """启动调度器"""
        logger.info("开始启动调度器...")
        session = get_session()
        try:
            # 获取所有启用了总结功能的规则
            rules = session.query(ForwardRule).filter_by(is_summary=True).all()
            logger.info(f"找到 {len(rules)} 个启用了总结功能的规则")
            
            for rule in rules:
                logger.info(f"正在为规则 {rule.id} ({rule.source_chat.name} -> {rule.target_chat.name}) 创建调度任务")
                logger.info(f"总结时间: {rule.summary_time}")
                
                # 计算下一次执行时间
                now = datetime.now(self.timezone)
                next_time = self._get_next_run_time(now, rule.summary_time)
                wait_seconds = (next_time - now).total_seconds()
                
                logger.info(f"下一次执行时间: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"等待时间: {wait_seconds:.2f} 秒")
                
                await self.schedule_rule(rule)
                
            if not rules:
                logger.info("没有找到启用了总结功能的规则")
            
            logger.info("调度器启动完成")
        except Exception as e:
            logger.error(f"启动调度器时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
        finally:
            session.close()
            
    def stop(self):
        """停止所有任务"""
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()

    async def execute_all_summaries(self):
        """立即执行所有启用了总结功能的规则"""
        session = get_session()
        try:
            rules = session.query(ForwardRule).filter_by(is_summary=True).all()
            logger.info(f"开始执行 {len(rules)} 个总结任务")
            
            for rule in rules:
                try:
                    await self._execute_summary(rule)
                except Exception as e:
                    logger.error(f"执行规则 {rule.id} 的总结任务时出错: {str(e)}")
                    continue
                    
            logger.info("所有总结任务执行完成")
        finally:
            session.close() 