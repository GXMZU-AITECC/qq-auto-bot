# 🧪 sandbox 分支说明

`sandbox` 是本仓库的**常驻实验分支**：给想随便试功能的同学一个安全沙盒——随便折腾，绝不碰生产。

## 定位

- **零业务**：只有基础 API（连 QQ、收发消息、功能自动发现），没有任何现成业务功能。
- **只进不出**：你可以往 `sandbox` 提任何功能；但 `sandbox` **永不合并回** `main` / `develop`。
- **基础代码独立**：从 `develop` 切出后，基础 API 在本线自行维护，与生产**互不同步**。

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

3. 写功能优先放在 `features/<名>/`（配套配置放 `configs/<名>.yaml`）；确有需要也可以改基础 API。
4. 推送并**向 `sandbox` 提 PR**（base 选 `sandbox`），**CI 通过即可合并**。

> 所有改动都走 PR 合并进 `sandbox`，不要直接推 `sandbox`。

## 约定（护栏）

- **基础 API 可以改**：`main.py` / `bot.py` / `config.py` / `features/__init__.py` 不是禁区——现有接口缺功能时，可以直接改或新增；尽量别破坏已有用法，并在 PR 里说明改了什么、为什么。
- **命令加前缀**：用 `/play` 之类的前缀，避免和将来的生产指令撞名。
- **功能开关**：`configs/<功能>.yaml` 用 `enabled` 控制启停，`true` 直接启用、`false` 关闭；新功能可以直接 `enabled: true`。

## 基础 API 怎么维护

`sandbox` 与 `develop` 是两条独立的线，基础 API 各自维护、互不同步。功能开发需要但框架没有的接口，可以直接在 `sandbox` 线补上，和功能改动放在同一个 PR 里即可。

## 好点子怎么上生产

**贡献者不直接向生产分支（`main` / `develop`）提代码**——生产代码只由维护者维护。

`sandbox` 里玩成熟的好点子，交给维护者评估：**是否移植、怎么移植由维护者决定**，你不必、也不要自己去开生产 PR。
