"""校历查询：群里问「今天上课吗」，机器人按校历回答（含调休补课）。

判定优先级：**学校特有假期 > 学校特有调休补班 > 不在学期内 > (通用节假日/周末) > 正常教学日**。
通用节假日和全国调休复用 features.scheduled.calendar 的接口，学校特有的寒暑假和调休保留在本配置。

校历数据写在 configs/schoolcalendar.yaml，人工维护，每次查询现读（改配置不用重启）。

命令（与 demo / easteregg 一致，不带斜杠）：
    校历          今天的状态 + 第几教学周
    调休          列出本学期所有调休补班日期
    今天上课吗    自然语言问法，也支持「明天」「后天」
"""

import logging
from datetime import date, timedelta

from config import load_feature_config
from features.scheduled.calendar import ensure, is_workday

logger = logging.getLogger("features.schoolcalendar")

CFG_NAME = "schoolcalendar"
WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
DAY_OFFSET = {"今天": 0, "明天": 1, "后天": 2}


def _to_date(value):
    """把配置里的日期值转成 date，支持 date / 'YYYY-MM-DD' / 'YYYY/MM/DD'。

    解析不了返回 None，调用方跳过即可，不让坏数据炸掉整个功能。
    """
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip().replace("/", "-")
        parts = raw.split("-")
        if len(parts) < 3:
            return None
        try:
            year, month, day = (int(p) for p in parts[:3])
            return date(year, month, day)
        except ValueError:
            return None
    return None


def _norm_weekday(value):
    """把配置里的 for_weekday 归一成「周X」，支持 周四 / 星期四 / 4 / '4'。

    解析不了返回 None —— 补班判定照样生效，只是回复里不显示补哪天的课。
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return WEEKDAY_NAMES[value - 1] if 1 <= value <= 7 else None
    if isinstance(value, str):
        raw = value.strip()
        if raw in WEEKDAY_NAMES:
            return raw
        if raw.isdigit():
            n = int(raw)
            return WEEKDAY_NAMES[n - 1] if 1 <= n <= 7 else None
        # 兼容「星期四」这类写法
        tail = raw[-1] if raw else ""
        for name in WEEKDAY_NAMES:
            if name.endswith(tail):
                return name
    return None


def _point_entries(cfg, key):
    """解析单日条目（调休补班）。

    [{'date':..., 'name':..., 'for_weekday':...}] → [(date, name, for_weekday)]
    其中 for_weekday 是「周X」或 None，表示这天补周几的课。
    """
    out = []
    for item in cfg.get(key) or []:
        if not isinstance(item, dict):
            continue
        day = _to_date(item.get("date"))
        if day is None:
            continue
        out.append(
            (
                day,
                str(item.get("name") or "").strip(),
                _norm_weekday(item.get("for_weekday")),
            )
        )
    return out


def _range_entries(cfg, key):
    """解析区间条目（假期）：[{'from':..., 'to':..., 'name':...}] → [(start, end, name)]。"""
    out = []
    for item in cfg.get(key) or []:
        if not isinstance(item, dict):
            continue
        start = _to_date(item.get("from"))
        end = _to_date(item.get("to") or item.get("from"))
        if start is None or end is None or end < start:
            continue
        out.append((start, end, str(item.get("name") or "").strip()))
    return out


def semester_info(day, cfg):
    """算学期区间与教学周次。配置缺失或不合法时返回 None。"""
    sem = cfg.get("semester") or {}
    start = _to_date(sem.get("start"))
    try:
        weeks = int(sem.get("weeks") or 0)
    except (TypeError, ValueError):
        weeks = 0
    if start is None or weeks <= 0:
        return None

    end = start + timedelta(days=weeks * 7 - 1)
    in_range = start <= day <= end
    return {
        "name": str(sem.get("name") or "本学期"),
        "start": start,
        "end": end,
        "weeks": weeks,
        "in_range": in_range,
        "week": (day - start).days // 7 + 1 if in_range else None,
    }


async def judge(day, cfg):
    """判定某天上课还是放假，返回 (状态, 原因)。

    状态只有三种：上课 / 放假 / 不在学期内。
    """
    info = semester_info(day, cfg)

    # 1. 学校特有的放假区间（如寒暑假、校运会等）
    for start, end, name in _range_entries(cfg, "holidays"):
        if start <= day <= end:
            return "放假", name or "假期"

    # 2. 学校特有的调休补班（周末上课）
    for makeup_day, name, for_weekday in _point_entries(cfg, "makeups"):
        if makeup_day == day:
            reason = name or "调休补班"
            if for_weekday:
                reason = f"{reason}，上{for_weekday}的课"
            return "上课", reason

    # 3. 学期区间外一律不算上课，避免误报
    if info is None or not info["in_range"]:
        return "不在学期内", ""

    # 4. 复用通用节假日/调休接口
    # 先 await ensure(year) 确保缓存就绪，再判断
    await ensure(day.year)
    is_work = is_workday(day)

    if is_work is True:
        return "上课", "正常教学日"
    elif is_work is False:
        return "放假", "周末或法定节假日"
    else:
        # 5. 未知情况（None）降级：使用原有的周末判断兜底
        if day.weekday() >= 5:
            return "放假", "周末"
        return "上课", "正常教学日"


def _fmt_day(day):
    return f"{day.isoformat()}（{WEEKDAY_NAMES[day.weekday()]}）"


async def _fmt_result(day, cfg):
    """把某天的判定结果拼成一行，供 /校历 与自然语言问法共用。"""
    status, reason = await judge(day, cfg)
    line = f"{_fmt_day(day)} · {status}"
    if reason:
        line += f"（{reason}）"
    return line


async def cmd_calendar(bot, group_id, user_id, text):
    """校历：今天的状态 + 本学期第几教学周。"""
    cfg = load_feature_config(CFG_NAME)
    if not cfg.get("enabled", False):
        return None

    today = date.today()
    lines = [await _fmt_result(today, cfg)]

    info = semester_info(today, cfg)
    if info is None:
        # 配置缺失是维护者要处理的事，只进后台日志，不发到群里
        logger.warning(
            "校历未配置：请在 configs/schoolcalendar.yaml 填写 semester.start 与 weeks"
        )
    elif info["in_range"]:
        lines.append(f"📖 {info['name']} · 第 {info['week']} 教学周（共 {info['weeks']} 周）")
    else:
        lines.append(
            f"📖 {info['name']} 的区间是 {info['start'].isoformat()} ~ {info['end'].isoformat()}"
        )

    return "\n".join(lines)


async def cmd_makeups(bot, group_id, user_id, text):
    """调休：列出本学期所有调休补班日期，并说明补周几的课。"""
    cfg = load_feature_config(CFG_NAME)
    if not cfg.get("enabled", False):
        return None

    entries = sorted(_point_entries(cfg, "makeups"), key=lambda e: e[0])
    if not entries:
        return "本学期没有配置调休补班安排。"

    lines = ["📌 本学期调休补班安排："]
    for day, name, for_weekday in entries:
        parts = [_fmt_day(day)]
        if name:
            parts.append(name)
        if for_weekday:
            parts.append(f"上{for_weekday}的课")
        lines.append("  · " + " ".join(parts))
    return "\n".join(lines)


async def cmd_ask(bot, group_id, user_id, text):
    """「今天上课吗」「明天有课吗」这类自然语言问法。"""
    cfg = load_feature_config(CFG_NAME)
    if not cfg.get("enabled", False):
        return None

    offset = 0
    for word, value in DAY_OFFSET.items():
        if text.startswith(word):
            offset = value
            break

    target = date.today() + timedelta(days=offset)
    return await _fmt_result(target, cfg)


# ★ 精确命令（不带斜杠，与 demo / easteregg 的现有指令风格保持一致）
COMMANDS = {
    "校历": cmd_calendar,
    "调休": cmd_makeups,
}

# ★ 正则命令：整条消息全匹配才触发
COMMAND_PATTERNS = {
    r"^(今天|明天|后天)(上课|有课)吗[?？]?$": cmd_ask,
}