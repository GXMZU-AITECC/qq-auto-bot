# 定时消息功能

后台长驻任务，按 cron 到点自动往群里 / 私聊发消息。开启 `workday: true` 时，当天是否发送由**节假日日历**决定，能正确处理**调休**：法定节假日（工作日）不发，调休补班的周末照发。

## 配置

编辑 `configs/scheduled.yaml`（示例模板），或复制为 `configs/scheduled.local.yaml` 填真实值——
`.local.yaml` 会被优先加载且已 `.gitignore`（不入库）。改动后无需重启（每轮热加载）。

```yaml
calendar_sources:
  - "https://timor.tech/api/holiday/year/{year}/"
  - "https://api.apihubs.cn/holiday/get?year={year}&size=400"

scheduled_messages:
  - name: "早间到岗提醒"      # 唯一名，用于去重与日志
    enable: true             # 每轮热加载，可随时改
    type: group              # group=群聊 / private=私聊
    target: 626523274        # 群号或 QQ 号
    cron: "30 7 * * 1-5"     # 5 段：分 时 日 月 周
    workday: true            # true=按日历(含调休)，日历未知则回退 cron 周字段
    message: |
      【定时消息】新的一天，注意按时到岗。
      [CQ:image,file=file:///C:/path/to/image.png]
```

字段说明：

| 字段 | 默认 | 说明 |
|------|------|------|
| `name` | 必填 | 唯一名，用于去重与日志 |
| `enable` | `true` | 单条开关，每轮热加载 |
| `type` | `group` | `group`=群聊 / `private`=私聊 |
| `target` | 必填 | 群号或 QQ 号 |
| `cron` | 必填 | 5 段标准 cron：分 时 日 月 周 |
| `workday` | `false` | `true` 时按日历决定当天是否发（见下） |
| `message` | 必填 | 消息内容，支持换行与 CQ 码 |

缺 `name` / `target` / `cron` / `message` 的条目会被跳过；cron 非法也会跳过，不影响其它条目。可定义**多条**定时消息。

## 发送语义

`workday: false`（省略）：时间 + 日期都按完整 cron（沿用旧 AutoReply 行为）。

`workday: true`：**时间（分/时）永远按 cron 匹配**；**当天是否发**优先由日历决定，日历不可用时回退到 cron 的日/月/周字段。

| workday | 日历 | 今天 | 发不发 |
|---------|------|------|--------|
| `true` | 已知 | 工作日 / 调休补班（如周末上班） | ✅ |
| `true` | 已知 | 周末 / 法定节假日 | ❌ |
| `true` | 未知 | — | 回退 cron 周字段（如 `1-5` → 只在周一到五发） |
| `false` | — | — | 按完整 cron |

> ⚠️ 因为未知时会回退到 cron 的周字段，`workday: true` 的条目**请保留有意义的周字段**（如 `1-5`），别写 `*`，否则日历缺失时会退化成"每天发"。

## 节假日日历

- **数据源**：`calendar_sources` 按序尝试，默认 timor.tech（主）+ apihubs（备选）；换源只改配置、不改代码。
- **磁盘缓存**：按年存 `data/calendar/{year}.json`，内容为 `{"year": 2026, "days": {"2026-10-01": true, ...}}`，只存**特殊日**（节假日 + 调休补班），普通日查询时用 `weekday()<5` 现算。
- **按需刷新**：一年数据一经发布即固定，**只在缺该年缓存时拉取一次**（约 1 次/年）；断网日靠缓存顶。
- **跨年预取**：从每年 11 月起，每天尝试预取次年数据；未发布则拉空不缓存，隔天再试，发布后写入即止。
- **未知兜底**：日历不可用时 `is_workday` 返回"未知"，由上层回退到 cron 周字段（见上）。

## 实现说明

- 长驻 asyncio 循环，睡到下一分钟边界触发；同一分钟只处理一次（重复唤醒自动去重）。
- 时区固定 `UTC+8`（中国无夏令时），任意主机时区下都正确。
- 启动时刷新当年数据，之后每天变更时后台刷新，不阻塞发送。

> 若旧的 Mirai AutoReply 插件仍在运行同名 cron，会**重复发送**——请禁用其 `cron.json` 中的对应条目。
