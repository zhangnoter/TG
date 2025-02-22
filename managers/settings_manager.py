import os
from utils.settings import load_ai_models
from enums.enums import ForwardMode, MessageMode, PreviewMode
from models.models import get_session
from telethon import Button

AI_MODELS = load_ai_models()

# 规则配置字段定义
RULE_SETTINGS = {
    'mode': {
        'display_name': '转发模式',
        'values': {
            ForwardMode.WHITELIST: '白名单',
            ForwardMode.BLACKLIST: '黑名单'
        },
        'toggle_action': 'toggle_mode',
        'toggle_func': lambda current: ForwardMode.BLACKLIST if current == ForwardMode.WHITELIST else ForwardMode.WHITELIST
    },
    'use_bot': {
        'display_name': '转发方式',
        'values': {
            True: '使用机器人',
            False: '使用用户账号'
        },
        'toggle_action': 'toggle_bot',
        'toggle_func': lambda current: not current
    },
    'is_replace': {
        'display_name': '替换模式',
        'values': {
            True: '开启',
            False: '关闭'
        },
        'toggle_action': 'toggle_replace',
        'toggle_func': lambda current: not current
    },
    'message_mode': {
        'display_name': '消息模式',
        'values': {
            MessageMode.MARKDOWN: 'Markdown',
            MessageMode.HTML: 'HTML'
        },
        'toggle_action': 'toggle_message_mode',
        'toggle_func': lambda current: MessageMode.HTML if current == MessageMode.MARKDOWN else MessageMode.MARKDOWN
    },
    'is_preview': {
        'display_name': '预览模式',
        'values': {
            PreviewMode.ON: '开启',
            PreviewMode.OFF: '关闭',
            PreviewMode.FOLLOW: '跟随原消息'
        },
        'toggle_action': 'toggle_preview',
        'toggle_func': lambda current: {
            PreviewMode.ON: PreviewMode.OFF,
            PreviewMode.OFF: PreviewMode.FOLLOW,
            PreviewMode.FOLLOW: PreviewMode.ON
        }[current]
    },
    'is_original_link': {
        'display_name': '原始链接',
        'values': {
            True: '附带',
            False: '不附带'
        },
        'toggle_action': 'toggle_original_link',
        'toggle_func': lambda current: not current
    },
    'is_delete_original': {
        'display_name': '删除原始消息',
        'values': {
            True: '开启',
            False: '关闭'
        },
        'toggle_action': 'toggle_delete_original',
        'toggle_func': lambda current: not current
    },
    'is_ufb': {
        'display_name': 'UFB同步',
        'values': {
            True: '开启',
            False: '关闭'
        },
        'toggle_action': 'toggle_ufb',
        'toggle_func': lambda current: not current
    },
    'is_original_sender': {
        'display_name': '原始发送者',
        'values': {
            True: '显示',
            False: '隐藏'
        },
        'toggle_action': 'toggle_original_sender',
        'toggle_func': lambda current: not current
    },
    'is_original_time': {
        'display_name': '发送时间',
        'values': {
            True: '显示',
            False: '隐藏'
        },
        'toggle_action': 'toggle_original_time',
        'toggle_func': lambda current: not current
    }
}


# 添加 AI 设置
AI_SETTINGS = {
    'is_ai': {
        'display_name': 'AI处理',
        'values': {
            True: '开启',
            False: '关闭'
        },
        'toggle_action': 'toggle_ai',
        'toggle_func': lambda current: not current
    },
    'ai_model': {
        'display_name': 'AI模型',
        'values': {
            None: '默认',
            '': '默认',
            **{model: model for model in AI_MODELS}
        },
        'toggle_action': 'change_model',
        'toggle_func': None
    },
    'ai_prompt': {
        'display_name': 'AI提示词',
        'values': {
            None: os.getenv('DEFAULT_AI_PROMPT'),
            '': os.getenv('DEFAULT_AI_PROMPT'),
        },
        'toggle_action': 'set_prompt',
        'toggle_func': None
    },
    'is_keyword_after_ai': {
        'display_name': 'AI处理后再次执行关键字过滤',
        'values': {
            True: '开启',
            False: '关闭'
        },
        'toggle_action': 'toggle_keyword_after_ai',
        'toggle_func': lambda current: not current
    },
    'is_summary': {
        'display_name': 'AI总结',
        'values': {
            True: '开启',
            False: '关闭'
        },
        'toggle_action': 'toggle_summary',
        'toggle_func': lambda current: not current
    },
    'summary_time': {
        'display_name': '总结时间',
        'values': {
            None: '00:00',
            '': '00:00'
        },
        'toggle_action': 'set_summary_time',
        'toggle_func': None
    },
    'summary_prompt': {
        'display_name': 'AI总结提示词',
        'values': {
            None: os.getenv('DEFAULT_SUMMARY_PROMPT'),
            '': os.getenv('DEFAULT_SUMMARY_PROMPT'),
        },
        'toggle_action': 'set_summary_prompt',
        'toggle_func': None
    }
}

async def create_settings_text(rule):
    """创建设置信息文本"""
    text = (
        "📋 管理转发规则\n\n"
        f"规则ID: `{rule.id}`\n" 
        f"目标聊天: {rule.target_chat.name}\n"
        f"源聊天: {rule.source_chat.name}"
    )
    return text

async def create_buttons(rule):
    """创建规则设置按钮"""
    buttons = []

    # 获取当前聊天的当前选中规则
    session = get_session()
    try:
        target_chat = rule.target_chat
        current_add_id = target_chat.current_add_id
        source_chat = rule.source_chat

        # 添加规则切换按钮
        is_current = current_add_id == source_chat.telegram_chat_id
        buttons.append([
            Button.inline(
                f"{'✅ ' if is_current else ''}应用当前规则",
                f"toggle_current:{rule.id}"
            )
        ])

        # 转发模式和转发方式放在一行
        buttons.append([
            Button.inline(
                f"📥 转发模式: {RULE_SETTINGS['mode']['values'][rule.mode]}",
                f"toggle_mode:{rule.id}"
            ),
            Button.inline(
                f"🤖 转发方式: {RULE_SETTINGS['use_bot']['values'][rule.use_bot]}",
                f"toggle_bot:{rule.id}"
            )
        ])

        # 其他设置两两一行
        if rule.use_bot:  # 只在使用机器人时显示这些设置
            buttons.append([
                Button.inline(
                    f"🔄 替换模式: {RULE_SETTINGS['is_replace']['values'][rule.is_replace]}",
                    f"toggle_replace:{rule.id}"
                ),
                Button.inline(
                    f"📝 消息格式: {RULE_SETTINGS['message_mode']['values'][rule.message_mode]}",
                    f"toggle_message_mode:{rule.id}"
                )
            ])

            buttons.append([
                Button.inline(
                    f"👁 预览模式: {RULE_SETTINGS['is_preview']['values'][rule.is_preview]}",
                    f"toggle_preview:{rule.id}"
                ),
                Button.inline(
                    f"🔗 原始链接: {RULE_SETTINGS['is_original_link']['values'][rule.is_original_link]}",
                    f"toggle_original_link:{rule.id}"
                )
            ])

            buttons.append([
                Button.inline(
                    f"👤 原始发送者: {RULE_SETTINGS['is_original_sender']['values'][rule.is_original_sender]}",
                    f"toggle_original_sender:{rule.id}"
                ),
                Button.inline(
                    f"⏰ 发送时间: {RULE_SETTINGS['is_original_time']['values'][rule.is_original_time]}",
                    f"toggle_original_time:{rule.id}"
                )
            ])

            buttons.append([
                Button.inline(
                    f"🗑 删除原消息: {RULE_SETTINGS['is_delete_original']['values'][rule.is_delete_original]}",
                    f"toggle_delete_original:{rule.id}"
                ),
                Button.inline(
                    f"🔄 UFB同步: {RULE_SETTINGS['is_ufb']['values'][rule.is_ufb]}",
                    f"toggle_ufb:{rule.id}"
                )
            ])

            # AI设置单独一行
            buttons.append([
                Button.inline(
                    "🤖 AI设置",
                    f"ai_settings:{rule.id}"
                )
            ])

        # 删除规则和返回按钮
        buttons.append([
            Button.inline(
                "❌ 删除规则",
                f"delete:{rule.id}"
            )
        ])

        buttons.append([
            Button.inline(
                "👈 返回",
                "settings"
            )
        ])

    finally:
        session.close()

    return buttons
