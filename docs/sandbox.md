# 🧪 sandbox 分支说明

`sandbox` 是本仓库的**常驻实验分支**：给想随便试功能的同学一个安全沙盒——随便折腾，绝不碰生产。

## 定位

- **零业务**：只有基础 API（连 QQ、收发消息、功能自动发现），没有任何现成业务功能。
- **只进不出**：你可以往 `sandbox` 提任何功能；但 `sandbox` **永不合并回** `main` / `develop`。
- **同一套基础代码**：从 `develop` 切出，框架与 API 跟生产完全一致，写出来的功能将来能直接搬去生产。

生产 = `main` + `develop`，与 `sandbox` 互不影响。

## 怎么参与

1. 从最新 `sandbox` 拉你自己的分支：

   ```bash
   git fetch origin
   git switch -c feature/myfeature origin/sandbox
   ```

2. 写功能，只放在 `features/<名>/`（配套配置放 `configs/<名>.yaml`）。
3. 推送并向 `sandbox` 提 PR，**CI 通过即可合并**。

> 所有改动都走 PR 合并进 `sandbox`，不要直接推 `sandbox`。

## 约定（护栏）

- **别改基础 API**：`main.py` / `bot.py` / `config.py` / `features/__init__.py` 由维护者统一维护；你的 PR 只碰 `features/` 和 `configs/`。
- **命令加前缀**：用 `/play` 之类的前缀，避免和将来的生产指令撞名。
- **默认关闭**：功能配置里以 `enabled: false` 起手，想用时再开。

## 基础 API 怎么更新

`sandbox` 与 `develop` 是两条独立的线。当 `develop` 更新了基础 API（框架 / `bot.py` / `config.py` 等），**由维护者把同样的改动也提交到 `sandbox`**，即"**改 API 时两边一起改**"。

- 为什么手动：自动同步容易把业务代码也带过来；手动最干净。
- 代价：靠纪律，改动多时别漏。

## 好点子怎么上生产

`sandbox` 里玩成熟的功能，**另提一个正式 PR 进 `develop`**（不是合并 `sandbox`），走生产的评审流程。
