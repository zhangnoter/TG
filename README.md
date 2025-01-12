![img](./logo/png/logo-title.png)

<h3><div align="center">Telegram 转发器 | Telegram Forwarder</div>

---

<div align="center">

[![Docker](https://img.shields.io/badge/-Docker-2496ED?style=flat-square&logo=docker&logoColor=white)][docker-url]

[docker-url]: https://hub.docker.com/r/heavrnl/telegramforwarder

</div>

## 简介
Telegram 转发器是一个消息转发工具，可以将指定聊天中的消息转发到其他聊天。

- 🔄 **多源转发**：支持从多个来源转发到指定目标
- 🔍 **关键词过滤**：支持白名单和黑名单模式
- 📝 **消息格式**：支持 Markdown 和 HTML 格式
- 📋 **正则替换**：支持使用正则表达式替换消息内容
- 🔗 **联动同步**：支持与[通用论坛屏蔽插件](https://github.com/heavrnl/universalforumblock)联动同步，实现三端屏蔽

## 快速开始

### 1. 配置环境

新建.env文件，填写参数
```ini
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

```yaml
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
    stdin_open: true
    tty: true
```

### 2. 启动服务

首次运行（需要验证）：

第一次初始化容器，输入验证码
```bash
docker-compose run -it telegram-forwarder
```
CTRL+C 退出容器

修改 docker-compose.yml 文件，修改 `stdin_open: false` 和 `tty: false`

后台运行：
```bash
docker-compose up -d
```

## 使用说明
