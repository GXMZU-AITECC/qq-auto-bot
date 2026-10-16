# 🧪 sandbox 分支说明

`sandbox` 是本仓库的**常驻实验分支**：给想随便试功能的同学一个安全沙盒——随便折腾，绝不碰生产。

## 定位

- **零业务**：只有基础 API（连 QQ、收发消息、功能自动发现），没有任何现成业务功能。
- **只进不出**：你可以往 `sandbox` 提任何功能；但 `sandbox` **永不合并回** `main` / `develop`。
- **基础 API 与生产分叉**：本线连的是**官方 QQ 机器人平台（botpy）**，生产（`main` / `develop`）连 LLOneBot。写 `features/` 的契约一致，纯文本功能可直接搬去生产；用到平台专属能力的需适配。

生产 = `main` + `develop`，与 `sandbox` 互不影响。

## 怎么参与

1. 拿到代码（切到 `sandbox`）：

   ```bash
   # 方式一：直接 clone sandbox
   git clone -b sandbox https://github.com/GXMZU-AITECC/qq-auto-bot.git
   cd qq-auto-bot

   # 方式二：先 clone 再切
   git clone https://github.com/GXMZU-AITECC/qq-auto-bot.git
   cd qq-auto-bot
   git switch sandbox
   ```

2. 从 `sandbox` 新建你自己的分支：

   ```bash
   git switch -c feature/myfeature
   ```

3. 写功能，只放在 `features/<名>/`（配套配置放 `configs/<名>.yaml`）。
4. 推送并**向 `sandbox` 提 PR**（base 选 `sandbox`），**CI 通过即可合并**。

> 所有改动都走 PR 合并进 `sandbox`，不要直接推 `sandbox`。

## 约定（护栏）

- **别改基础 API**：`main.py` / `bot_official.py` / `config.py` / `features/__init__.py` 由维护者统一维护；你的 PR 只碰 `features/` 和 `configs/`。
- **命令加前缀**：用 `/play` 之类的前缀，避免和将来的生产指令撞名。
- **默认关闭**：功能配置里以 `enabled: false` 起手，想用时再开。

## 基础 API 怎么维护

`sandbox` 线与 `main` / `develop` 是**完全独立的两条线，基础 API 已分叉**：

- 本线：官方 QQ 机器人平台（botpy），客户端是 `bot_official.py`。
- 生产：LLOneBot（客户端 `bot.py`），**不在本线**。

因此**两边的基础 API 各自维护、互不同步**——本线的框架改动只在本线内流转（`feature/*` → `sandbox`），不会也不该回灌生产。

## 好点子怎么上生产

**贡献者不直接向生产分支（`main` / `develop`）提代码**——生产代码只由维护者维护。

`sandbox` 里玩成熟的好点子，交给维护者评估：**是否移植、怎么移植由维护者决定**，你不必、也不要自己去开生产 PR。
