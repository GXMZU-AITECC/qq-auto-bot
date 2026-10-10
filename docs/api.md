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

### 后台长驻任务（可选 `STARTUP`）

功能要自己按时间干活（非消息驱动）时，导出 `STARTUP` 列表：

```python
async def run(bot):
    while True:
        await asyncio.sleep(60)
        ...

STARTUP = [run]      # 启动时 create_task，退出时自动 cancel
```

- 每项签名 `async def fn(bot) -> None`，内部自己写循环。
- 异常被捕获并记日志，不影响其它任务。
- 别在 import 阶段执行网络 / IO。

---

## 🤖 bot 对象（bot.py）

发消息和查信息全靠它。

### `bot.send_group_msg(group_id, text)`

发送群消息。

```python
await bot.send_group_msg("123456789", "你好")
```

### `bot.send_private_msg(user_id, text)`

发送私聊消息。

```python
await bot.send_private_msg("10001", "你好")
```

### `bot.get_group_member_name(group_id, user_id)`

获取群成员昵称（优先群名片，其次 QQ 昵称）。

```python
name = await bot.get_group_member_name("123456789", "10001")
# → "张三"
```

### `bot._api_call(action, params)`

直接调 OneBot API（一般用不到）。

```python
await bot._api_call("set_group_card", {"group_id": 123, "user_id": 456, "card": "新名片"})
```

---

## ⚙️ config 模块（config.py）

### `get(*keys, default=None)`

读全局配置 `config.yaml`。

```python
from config import get
ws = get("llonebot", "ws_url")                    # → "ws://127.0.0.1:3001"
file = get("data", "file", default="data.db")      # 取不到时返回默认值
```

### `load_feature_config(name)`

读功能配置 `configs/{name}.yaml`。

```python
from config import load_feature_config
cfg = load_feature_config("checkin")
shifts = cfg.get("checkin_shifts", [])
```

找不到配置文件时返回空字典 `{}`，不会报错。

---

## 🔍 自动发现引擎（features/__init__.py）

### `discover()`

扫描 `features/` 下所有子包，收集 `COMMANDS`（精确）与 `COMMAND_PATTERNS`（正则）。启动时自动调用，一般不需要手动调。

### `dispatch(bot, group_id, user_id, text)`

路由消息到对应的命令处理器。先精确匹配 `COMMANDS`，再按注册顺序依次尝试 `COMMAND_PATTERNS` 的正则全匹配，都找不到返回 `None`。

### `startups()`

返回各功能注册的 `STARTUP` 协程列表（`async def fn(bot) -> None`）。由 `main.py` 在启动时拉起、退出时取消，一般不需要手动调。
