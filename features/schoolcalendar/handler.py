"""校历查询：群里问「今天上课吗」，机器人按校历回答（含调休补课）。

判定优先级：**调休补班 > 放假区间 > 不在学期内 > 周末 > 正常教学日**。
这样调休补班的周末会被正确判成「上课」，而法定假期里的日子一律「放假」。

校历数据写在 configs/schoolcalendar.yaml，人工维护，每次查询现读（改配置不用重启）。

命令：
    /校历          今天的状态 + 第几教学周
    /调休          列出本学期所有调休补班日期
    今天上课吗     自然语言问法，也支持「明天」「后天」
"""

from datetime import date, timedelta

from config import load_feature_config

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


def _point_entries(cfg, key):
    """解析单日条目（调休补班）：[{'date':..., 'name':...}] → [(date, name)]。"""
    out = []
    for item in cfg.get(key) or []:
        if not isinstance(item, dict):
            continue
        day = _to_date(item.get("date"))
        if day is None:
            continue
        out.append((day, str(item.get("name") or "").strip()))
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


def judge(day, cfg):
    """判定某天上课还是放假，返回 (状态, 原因)。

    状态只有三种：上课 / 放假 / 不在学期内。
    """
    info = semester_info(day, cfg)

    # 1. 调休补班优先：周末也可能要上课
    for makeup_day, name in _point_entries(cfg, "makeups"):
        if makeup_day == day:
            return "上课", name or "调休补班"

    # 2. 放假区间（法定节假日、寒暑假等）
    for start, end, name in _range_entries(cfg, "holidays"):
        if start <= day <= end:
            return "放假", name or "假期"

    # 3. 学期区间外一律不算上课，避免误报
    if info is None or not info["in_range"]:
        return "不在学期内", ""

    # 4. 学期内的周末
    if day.weekday() >= 5:
        return "放假", "周末"

    return "上课", "正常教学日"


def _fmt_day(day):
    return f"{day.isoformat()}（{WEEKDAY_NAMES[day.weekday()]}）"


def _fmt_result(day, cfg):
    """把某天的判定结果拼成一行，供 /校历 与自然语言问法共用。"""
    status, reason = judge(day, cfg)
    line = f"{_fmt_day(day)} · {status}"
    if reason:
        line += f"（{reason}）"
    return line


async def cmd_calendar(bot, group_id, user_id, text):
    """/校历：今天的状态 + 本学期第几教学周。"""
    cfg = load_feature_config(CFG_NAME)
    if not cfg.get("enabled", False):
        return None

    today = date.today()
    lines = [_fmt_result(today, cfg)]

    info = semester_info(today, cfg)
    if info is None:
        lines.append("⚠️ 校历还没配好：请在 configs/schoolcalendar.yaml 填 semester.start 与 weeks")
    elif info["in_range"]:
        lines.append(f"📖 {info['name']} · 第 {info['week']} 教学周（共 {info['weeks']} 周）")
    else:
        lines.append(
            f"📖 {info['name']} 的区间是 {info['start'].isoformat()} ~ {info['end'].isoformat()}"
        )

    return "\n".join(lines)


async def cmd_makeups(bot, group_id, user_id, text):
    """/调休：列出本学期所有调休补班日期。"""
    cfg = load_feature_config(CFG_NAME)
    if not cfg.get("enabled", False):
        return None

    entries = sorted(_point_entries(cfg, "makeups"))
    if not entries:
        return "本学期没有配置调休补班安排。"

    lines = ["📌 本学期调休补班安排："]
    lines += [f"  · {_fmt_day(day)}{' ' + name if name else ''}" for day, name in entries]
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
    return _fmt_result(target, cfg)


# ★ 精确命令
COMMANDS = {
    "/校历": cmd_calendar,
    "/调休": cmd_makeups,
}

# ★ 正则命令：整条消息全匹配才触发
COMMAND_PATTERNS = {
    r"^(今天|明天|后天)(上课|有课)吗[?？]?$": cmd_ask,
}
