# 🤖 qq-auto-bot · sandbox（自由实验分支）

本分支是 qq-auto-bot 的**常驻实验分支**：一套现成的 QQ 机器人框架（LLOneBot + Python），
想做什么功能就做什么功能，**尽情玩，不影响生产**。

- 生产代码在 `main` / `develop`，本分支**永不合并回去**。
- 这里只有「基础 API」（连 QQ、收发消息、功能自动发现），**不含任何业务功能**。
- 玩成熟的好点子，再另提 PR 搬进生产。

## 一、获取代码

本仓库的默认分支不是 `sandbox`，clone 后要切过去：

```bash
git clone https://github.com/GXMZU-AITECC/qq-auto-bot.git
cd qq-auto-bot
git switch sandbox
```

已经 clone 过、只是没有这条分支的话：

```bash
git fetch origin
git switch sandbox
```

## 二、框架已经帮你做好这些

你只管写自己的功能，其余框架都包了：

- 连接 QQ（LLOneBot，OneBot v11）
- 收群消息、发群消息 / 私聊
- 按命令路由到你的处理函数（精确匹配 + 正则匹配）
- **内置 `/help`**：群里发 `/help` 自动列出所有已注册的命令
- 读 YAML 配置
- **功能自动发现**：功能丢进 `features/` 就生效，不用改 `main.py`

## 三、运行环境（不用你操心）

连接 QQ、登录 QQ、启动机器人进程都由**维护者统一负责**，你不需要自己启动。

你只管写 `features/` 下的功能代码即可；想本地自测时，装好 Python 依赖（Python 3.10+）：

```bash
pip install -r requirements.txt
```

## 四、3 步加第一个功能

完整教程见 [`docs/development.md`](docs/development.md)，现成范例见 `features/demo/`。速览：

1. 建目录 `features/myfeature/`
2. 写 `features/myfeature/handler.py`，导出 `COMMANDS`：

   ```python
   async def cmd_hello(bot, group_id, user_id, text):
       return "你好！"          # 返回字符串 = 机器人自动发到群里

   COMMANDS = {"/hello": cmd_hello}
   ```

3. 合并生效后，群里发 `/hello` 即会收到回复。

> 更多 API（发消息、取昵称、读配置）见 [`docs/api.md`](docs/api.md)。

## 五、怎么提交代码

1. 从 `sandbox` 拉你自己的分支：

   ```bash
   git fetch origin
   git switch -c feature/myfeature origin/sandbox
   ```

2. 写功能，只改 `features/` 和 `configs/`，**别动基础 API**（`main.py` / `bot.py` / `config.py` / `features/__init__.py`）。
3. 提交并推送：

   ```bash
   git add features/myfeature configs/myfeature.yaml
   git commit -m "feat: 我的新功能"
   git push -u origin feature/myfeature
   ```

4. 在 GitHub 上向 `sandbox` 提 PR，CI 通过即可合并。

详见 [`docs/sandbox.md`](docs/sandbox.md)。

## 六、目录结构

```
config.yaml          ← 全局配置
configs/             ← 各功能配置
features/            ← 你的功能都放这（自动发现）
  demo/              ← 范例功能
docs/                ← 文档
tests/               ← 单元测试
main.py              ← 启动入口（别改）
bot.py               ← 连 QQ（别改）
config.py            ← 读配置（别改）
```

## 七、文档

- [`docs/sandbox.md`](docs/sandbox.md) — 本分支的定位、玩法与约定
- [`docs/development.md`](docs/development.md) — 新手入门：3 步加新功能
- [`docs/api.md`](docs/api.md) — 框架 API 速查
- [`docs/qqbot-api.md`](docs/qqbot-api.md) — QQ 机器人 API 速查

## 许可证

本项目采用 [MIT 许可证](LICENSE)。
