# 🤖 qq-auto-bot

实验室群聊智能回复机器人二次开发项目，基于 LLOneBot (OneBot v11) + Python，支持功能模块自动发现，开箱即用。

## 📌 项目简介

本项目是面向实验室群聊的 QQ 机器人，内嵌自动回复与签到等实用功能。整体架构为「后端 LLOneBot 负责连接 QQ → Python 负责业务逻辑」，功能以子包形式组织在 `features/` 下，启动时自动发现，新增功能无需改动 `main.py`。

## 💻 设备依赖

- **操作系统**：Windows（另需能运行 LLOneBot 的环境）
- **Python**：3.10+（使用 `X | Y` 类型标注）
- **LLOneBot**：负责连接 QQ 并提供 OneBot v11 协议，默认开启端口 3000（HTTP API）与 3001（WebSocket）
- **Java 11+**：仅当使用 Overflow (Mirai) 后端时需要，详见 [`docs/mirai-deploy.md`](docs/mirai-deploy.md)
- **Python 依赖**：见 `requirements.txt`

| 依赖 | 用途 |
|------|------|
| websockets | 连接 LLOneBot 的 WebSocket |
| httpx | 调用 LLOneBot HTTP API |
| pyyaml | 读取 `config.yaml` / `configs/*.yaml` |
| fastapi / uvicorn | 网页数据统计服务 |
| openpyxl | 导出 Excel |

## ⚙️ 环境配置

1. 安装 Python 依赖：

```bash
pip install -r requirements.txt
```

2. 编辑 `config.yaml`，填写 LLOneBot 的连接地址等全局配置：

```yaml
llonebot:
  ws_url: ws://127.0.0.1:3001
  http_url: http://127.0.0.1:3000
```

3. 各功能的独立配置放在 `configs/` 下（如 `configs/checkin.yaml` 定义班次），改动后无需重启。

### 开发依赖

开发 / 提交代码前需装检查工具（运行时不需要）：

```bash
pip install -r requirements-dev.txt   # pytest、ruff
npm ci --prefix web                    # eslint
```

自查（与 CI 一致）：

```bash
ruff check .              # Python 静态检查
pytest -q                 # Python 单元测试
npm --prefix web run lint # 前端 JS 检查
```

## 🚀 使用方法

### 1. 启动后端（LLOneBot）

双击 `LLOneBot-win-x64-ffmpeg/llonebot.exe`，登录 QQ。

### 2. 启动机器人

```bash
python main.py
```

或双击根目录的 `start.bat`。

### 项目结构

```
config.yaml          ← 全局配置（含 web 网页服务配置）
configs/             ← 各功能独立配置
features/            ← 功能代码（自动发现，加新功能无需改 main.py）
web/                 ← 网页数据统计（FastAPI 后端 + 前端页面 + ESLint 配置）
docs/                ← 开发文档
tests/               ← 单元测试（pytest）
.github/             ← Issue/PR 模板、CI 工作流
pyproject.toml       ← ruff / pytest 配置
requirements.txt     ← 运行依赖
requirements-dev.txt ← 开发依赖（pytest、ruff）
```

### 已有功能

- [**签到**](docs/checkin.md) — 到岗发 `XX楼已到` 当场结算时长，每人每班次每天限一次；晚班带 `+2`/`+3` 自选时长
- **数据统计** — 网页查看所有数据表，支持分页浏览、按字段分组汇总、勾选字段导出 Excel（默认关闭）
- **Demo** — 功能开发示例（默认禁用，配置开启后输入 `/烤肠` 触发）

### 网页数据统计

默认关闭。启用方法：将 `config.yaml` 中 `web.enabled` 改为 `true` 后启动机器人，访问 `http://127.0.0.1:8000`。

- 左侧选择数据库和表查看数据，表格区域内部滚动，支持分页
- **数据** 模式：查看原始数据，表头可勾选字段，点击「导出 Excel」下载所选列
- **统计** 模式：选择「分组字段 + 汇总字段」自动汇总（如按 `user_id` 分组求和 `duration` 得到每人总时长），也可导出 Excel
- 只监听 `127.0.0.1`，仅本机可访问；库名/表名/字段名均做白名单校验

### 开发文档

详见 `docs/` 目录：

- [`development.md`](docs/development.md) — 新手入门，3 步加新功能
- [`api.md`](docs/api.md) — 框架 API 速查
- [`qqbot-api.md`](docs/qqbot-api.md) — QQ 机器人 API 速查
- [`mirai-deploy.md`](docs/mirai-deploy.md) — Overflow (Mirai) 部署与 AutoReply 自动回复教程

## 👥 维护团队

本项目由 **GXMZU-AITECC / qq-auto-bot** 团队维护，负责人及评审请求见 `.github/CODEOWNERS`。

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。
