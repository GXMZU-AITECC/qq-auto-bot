# 💬 QQ 机器人 API（OneBot v11）

机器人底层通过 LLOneBot 的 OneBot v11 协议与 QQ 交互。所有 API 可通过 `bot._api_call(动作, 参数)` 调用。

---

## ✉️ 发消息

### send_group_msg — 发群消息

```python
await bot._api_call("send_group_msg", {
    "group_id": 123456789,
    "message": "你好"
})
```

### send_private_msg — 发私聊

```python
await bot._api_call("send_private_msg", {
    "user_id": 10001,
    "message": "你好"
})
```

### send_group_forward_msg — 发合并转发

```python
await bot._api_call("send_group_forward_msg", {
    "group_id": 123456789,
    "messages": [...]     # 消息节点列表
})
```

---

## 📡 获取信息

### get_group_member_info — 群成员信息

```python
await bot._api_call("get_group_member_info", {
    "group_id": 123456789,
    "user_id": 10001,
})
# → { nickname: "昵称", card: "群名片", role: "member", ... }
```

### get_group_member_list — 群成员列表

```python
await bot._api_call("get_group_member_list", {
    "group_id": 123456789
})
# → [{ user_id, nickname, card, role }, ...]
```

### get_group_info — 群信息

```python
await bot._api_call("get_group_info", {
    "group_id": 123456789
})
# → { group_id, group_name, member_count, ... }
```

### get_group_list — 群列表

```python
await bot._api_call("get_group_list", {})
# → [{ group_id, group_name }, ...]
```

### get_stranger_info — 用户信息

```python
await bot._api_call("get_stranger_info", {
    "user_id": 10001
})
# → { user_id, nickname, sex, age }
```

---

## 🔧 操作群

### set_group_card — 设置群名片

```python
await bot._api_call("set_group_card", {
    "group_id": 123456789,
    "user_id": 10001,
    "card": "新名片"         # 空字符串可清空名片
})
```

### set_group_ban — 群禁言

```python
# duration 单位秒，0 表示解除禁言
await bot._api_call("set_group_ban", {
    "group_id": 123456789,
    "user_id": 10001,
    "duration": 600          # 10分钟
})
```

### set_group_whole_ban — 全员禁言

```python
await bot._api_call("set_group_whole_ban", {
    "group_id": 123456789,
    "enable": True
})
```

### set_group_admin — 设/取消管理员

```python
await bot._api_call("set_group_admin", {
    "group_id": 123456789,
    "user_id": 10001,
    "enable": True
})
```

---

## 🖼️ 消息格式

### 发送图片

```python
await bot._api_call("send_group_msg", {
    "group_id": 123456789,
    "message": [
        {"type": "text", "data": {"text": "看这张图："}},
        {"type": "image", "data": {"file": "http://..."}},
    ]
})
```

消息段类型：

| type | 说明 | data 字段 |
|------|------|-----------|
| text | 文本 | text |
| image | 图片 | file（本地路径/http/base64） |
| at | @某人 | qq（QQ号或 `all`） |
| reply | 回复 | id（消息ID） |

---

## 📌 说明

- `bot._api_call()` 返回 `dict`，含 `status`、`data`、`retcode` 字段
- 调用失败返回 `None`
- 完整 API 列表参考 [OneBot v11 标准](https://github.com/botuniverse/onebot-11)
