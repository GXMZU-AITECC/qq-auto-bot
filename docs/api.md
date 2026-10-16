# 📖 API 参考

---

## ✍️ 编写 Handler

每个功能需导出 `COMMANDS`（精确匹配）或 `COMMAND_PATTERNS`（正则匹配）字典：

```python
COMMANDS = {
    "/命令": 处理函数,
}

# 正则命令：键为正则字符串，消息全匹配时触发
COMMAND_PATTERNS = {
    r"^[\u4e00-\u9fa5]+楼已到$": 处理函数,
}
```

处理函数签名：

```python
async def 函数名(bot, group_id: str, user_id: str, text: str) -> str | None:
    ...
```

- `text` → 群友发送的原始消息全文（用不到就忽略）
- 返 `字符串` → 机器人自动发送到群里
- 返 `None` → 不回复

---

## 🤖 bot 对象

发消息和查信息全靠它。

### `bot.send_group_msg(group_id, text)`

发送群消息。

```python
await bot.send_group_msg("123456789", "你好")
```

### `bot.send_group_image(group_id, url)`

发送群图片（富媒体）。`url` 必须是**平台能下载到的公网地址**。

```python
await bot.send_group_image("123456789", "https://example.com/cat.png")
```

- 官方平台要「先上传换 `file_info`，再发 `msg_type=7`」，本方法已把两步封装好。
- 富媒体消息**不能同时带文本**：要「图文」就发两条（先 `send_group_msg` 再 `send_group_image`）。
- **只支持 URL**：本地图片文件暂不支持——botpy 的上传接口只收 `url`，想发本地图需自行研究 base64 / 分片上传。
- `file_info` 有时效，过期平台会拒绝；重新调用即可（会自动重传）。

### `bot.get_group_member_name(group_id, user_id)`

获取群成员昵称（官方平台无成员接口，返回消息里攒到的昵称，兜底返回 `user_id`）。

```python
name = await bot.get_group_member_name("123456789", "10001")
# → "张三"
```

---

## ⚙️ config 模块（config.py）

### `get(*keys, default=None)`

读全局配置 `config.yaml`。

```python
from config import get
level = get("log", "level")                        # → "INFO"
sandbox = get("qqbot", "sandbox", default=False)   # 取不到时返回默认值
```

### `load_feature_config(name)`

读功能配置 `configs/{name}.yaml`。

```python
from config import load_feature_config
cfg = load_feature_config("demo")       # 读 configs/demo.yaml
enabled = cfg.get("enabled", False)     # 取值，没有则返回默认
```

找不到配置文件时返回空字典 `{}`，不会报错。

---

## 🔍 自动发现引擎（features/__init__.py）

### `discover()`

扫描 `features/` 下所有子包，收集 `COMMANDS`（精确）与 `COMMAND_PATTERNS`（正则）。启动时自动调用，一般不需要手动调。

### `dispatch(bot, group_id, user_id, text)`

路由消息到对应的命令处理器。先处理内置命令 `/help`（列出所有已注册命令），再精确匹配 `COMMANDS`，最后按注册顺序依次尝试 `COMMAND_PATTERNS` 的正则全匹配，都找不到返回 `None`。

### 内置命令 `/help`

框架自带 `/help`，群里发 `/help` 即返回所有已注册的精确命令与正则命令；无需自己实现，且不能被功能注册覆盖。
