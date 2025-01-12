![img](./logo/png/logo-title.png)

<h3><div align="center">Telegram 转发器 | Telegram Forwarder</div>

---

<div align="center">

[![Docker](https://img.shields.io/badge/-Docker-2496ED?style=flat-square&logo=docker&logoColor=white)][docker-url]

[docker-url]: https://hub.docker.com/r/heavrnl/telegramforwarder

</div>

## 简介
Telegram 转发器主要作用是信息流过滤器，可以把任意指定聊天中的消息转发到另一个聊天。主要功能有：

- 支持白名单和黑名单模式
- 支持正则表达式匹配
- 支持替换关键字
- 支持消息发送时设置各自参数
- 支持与[通用论坛屏蔽插件](https://github.com/heavrnl/universalforumblock)联动同步，实现三端屏蔽

## 快速开始

新建.env文件，填写参数
```
# Telegram API 配置 (从 https://my.telegram.org/apps 获取)
API_ID=
API_HASH=

# 用户账号登录用的手机号 (格式如: +8613333333333)
PHONE_NUMBER=

# Bot Token
BOT_TOKEN=

# 用户ID (从 @userinfobot 获取)
USER_ID=

# 最大媒体文件大小限制（单位：MB），不填或0表示无限制
MAX_MEDIA_SIZE=

# 是否开启调试日志 (true/false)
DEBUG=false

# 数据库配置
DATABASE_URL=sqlite:///./db/forward.db


######### 扩展内容 #########

# 是否开启ufb (true/false)
UFB_ENABLED=false

# ufb服务器地址
UFB_SERVER_URL=

# ufb服务器用户API
UFB_TOKEN=

```

新建docker-compose.yml文件，内容如下：

```
services:
  telegram-forwarder:
    image: heavrnl/telegramforwarder:latest
    container_name: telegram-forwarder
    restart: unless-stopped
    volumes:
      - ./db:/app/db
      - ./.env:/app/.env
      - ./sessions:/app/sessions
      - ./temp:/app/temp
      - ./ufb/config:/app/ufb/config

```

