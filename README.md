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

# Telethon 用户账号登录用的手机号 (格式如: +8613812345678)
PHONE_NUMBER=

# Bot Token (可选，如果需要使用机器人功能，从 @BotFather 获取)
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

# 是否开启与通用论坛屏蔽插件服务端的同步服务 (true/false)
UFB_ENABLED=false
# 服务端地址
UFB_SERVER_URL=
# 用户API
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
### 使用实例

假设你想订阅频道 "TG 新闻" (https://t.me/tgnews)和 "TG 阅读" (https://t.me/tgread)，但想过滤掉一些不感兴趣的内容：

1. 创建一个 Telegram 群组/频道（例如："My TG Filter"）
2. 将机器人添加到群组/频道，并设置为管理员
3. 在群组/频道中发送命令：
   ```bash
   /bind https://t.me/tgnews
   /bind https://t.me/tgread
   ```
4. 设置消息处理模式：
   ```bash
   /settings
   ```
   选择要操作的对应频道的规则，根据喜好设置

5. 添加过滤关键词（黑名单模式下，包含这些关键词的消息将不被转发）：
   ```bash
   /add 广告 推广 优惠
   ```

6. 如果发现转发的消息格式有问题（比如有多余的符号），可以使用正则表达式处理：
   ```bash
   /replace \*\*
   ```
   这会删除消息中的所有 `**` 符号

>注意：以上增删改查操作，只对第一个绑定的规则生效，这里是TG NEWS，若想对TG READ进行操作，需要先使用`/switch`，选择TG READ，再进行操作增删改查，也可以使用`/add_all`，`/replace_all`等指令同时对两条规则生效
等同时对两条规则生效

这样，你就能在群组中收到经过过滤和格式化的频道消息了！

### 扩展内容

#### 与通用论坛屏蔽插件联动

确保.env文件中已配置相关参数，在已经绑定好的聊天窗口中使用`/ufb_bind <论坛域名>`，即可实现三端联动屏蔽，使用`/ufb_item_change`切换要同步当前域名的主页关键字/主页用户名/内容页关键字/内容页用户名
