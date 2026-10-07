# ☕ Overflow (Mirai) 后端部署

Overflow 是 Mirai Console 的一个分支，底层协议替换为 LLOneBot，上层的 Mirai 插件体系完全兼容。

---

## 🚀 启动

双击 `overflow-1.0.8/start.bat` 或终端运行：

```bash
cd overflow-1.0.8
start.bat
```

> 需要 Java 11+，根目录的 `jdk-11.0.27_windows-x64_bin.exe` 安装后即可使用。

---

## 🔗 与 LLOneBot 的关系

```
LLOneBot（协议层，连 QQ）
    ↑ WebSocket (ws://127.0.0.1:3001)
Overflow（插件层，跑 Mirai 插件）
```

先启动 **LLOneBot** 登录 QQ，再启动 **Overflow**。Overflow 会自动连上 LLOneBot。

---

## 📂 目录说明

| 目录 | 说明 |
|------|------|
| `plugins/` | 放 `.mirai2.jar` / `.mirai.jar` 插件 |
| `config/` | 各插件的配置文件 |
| `data/` | 插件运行时数据 |
| `logs/` | 运行日志 |
| `bots/` | 机器人账号数据（设备信息等） |
| `content/` | Over flow 和 Mirai 核心 JAR |

---

## 🔧 配置

### 连接 LLOneBot

`overflow.json`：

```json
{
    "ws_host": "ws://127.0.0.1:3001",
    "token": "你的token"
}
```

`ws_host` 和 LLOneBot 的 WebSocket 地址一致。

### 自动登录

`config/Console/AutoLogin.yml`：

```yaml
accounts:
  - qq: 123456789
    password: "你的密码"
```

### 插件设置

各插件配置在 `config/` 下对应的目录里，常见的：

| 配置路径 | 说明 |
|----------|------|
| `config/net.mamoe.mirai-api-http/setting.yml` | HTTP API 设置 |
| `config/Console/PermissionService.yml` | 权限管理 |
| `conf/auto_reply/conf.json` | 自动回复规则 |

---

## 📦 已有插件

| 插件 | 说明 |
|------|------|
| `mirai-api-http` | 提供 HTTP API 给外部程序调用 |
| `chat-command` | 群里发指令 |
| `AutoReply` | 关键词自动回复 |
| `mirai-administrator` | 群管理工具 |
| `lib-tts` | 文字转语音 |
| `mirai-login-solver-sakura` | 登录验证码处理 |

---

## 💬 AutoReply 自动回复

AutoReply 插件已内置在 `plugins/` 中，数据文件在 `conf/auto_reply/` 下。

### data.json — 关键词回复

顶层 key 是触发词（支持正则），每条规则的字段：

| 字段 | 说明 |
|------|------|
| `gid` | 目标群号，`0` 表示所有群 |
| `vss` | 回复列表（多条时随机选一条） |
| `vss[].data` | 回复内容，见下方格式 |
| `vss[].weight` | 权重，越大越容易被选中 |

**回复内容支持：**

| 格式 | 说明 |
|------|------|
| `文本内容` | 纯文本回复 |
| `[mirai:image:文件路径]` | 发送本地图片 |
| `[mirai:face:123]` | 发送 QQ 表情 |
| `[mirai:atall]` | @全体成员 |

示例：

```json
{
  "你好": {
    "gid": 123456789,
    "vss": [
      { "data": "你好呀", "state": 0, "weight": 1 },
      { "data": "哈喽~", "state": 0, "weight": 2 }
    ]
  },
  ".*草.*": {
    "gid": 0,
    "vss": [
      { "data": "注意素质", "state": 0, "weight": 1 }
    ]
  }
}
```

### cron.json — 定时消息

按 cron 表达式定时发消息：

```json
{
  "cron": "0 30 7 * * 1-5",
  "data": "大家早上好",
  "group": 123456789
}
```

cron 格式：`秒 分 时 日 月 周`，上面例子表示工作日 7:30 发送。

**开启 / 关闭定时消息：**

直接编辑 `cron.json`，操作完后保存即可，无需重启。

```json
// 关闭：在对象里加一个 "enable": false
{ "cron": "0 30 7 * * 1-5", "data": "大家早上好", "group": 123456789, "enable": false }

// 开启：把 "enable" 删掉或设为 true
{ "cron": "0 30 7 * * 1-5", "data": "大家早上好", "group": 123456789, "enable": true }

// 彻底删除：直接移除这条
```

> 插件热重载，改完即生效，不需要重启 Overflow。

### conf.json — 管理配置

```json
{
  "dataPath": "conf/auto_reply",
  "host": 10001,
  "follows": []
}
```

- `host` — 管理员的 QQ 号，管理员在群里发指令可增删关键词
- `follows` — 其他有管理权限的 QQ

> 修改 `data.json` 或 `cron.json` 后**无需重启**，插件会自动热重载。

## ⚠️ 注意事项

- **启动顺序：** 先 LLOneBot → 再 Overflow
- Overflow 本身不直接连 QQ，全靠 LLOneBot 转发
- 插件冲突时删除 `plugins/` 下对应的 `.jar` 即可禁用
