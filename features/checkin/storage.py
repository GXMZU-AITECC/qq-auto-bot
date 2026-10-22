import random
import re
import sqlite3
import os
from datetime import datetime, timedelta

from config import get, load_feature_config

TIMEZONE = timedelta(hours=8)
DB_FILE = get("data", "file", default="data/checkin_data.db")
RETAIN_DAYS = get("data", "retain_days", default=0)

TM_FMT = "%H:%M:%S"


# ---- 班次配置 ----

def _parse_hhmm(s: str) -> int:
    h, m = map(int, s.split(":"))
    return h * 60 + m


def shifts() -> list[dict]:
    """读取班次配置。到岗即结算。

    每个班次:
      hours       固定录入时长(白天班次)
      options     群友可选时长(晚班, 如 [2,3], 由 +N 后缀指定), 无则 None
      arrive_m    签到窗口开始
      leave_m     签到窗口截止(= 班次结束)
    """
    cfg = load_feature_config("checkin")
    shifts = []
    for s in cfg.get("checkin_shifts", []):
        shifts.append({
            "name": s["name"],
            "hours": s.get("duration_hours", 0),
            "options": tuple(sorted(s.get("options_hours", []))) if s.get("options_hours") else None,
            "arrive_m": _parse_hhmm(s["arrive"]),
            "leave_m": _parse_hhmm(s["leave"]),
        })
    return shifts


# ---- 时间 ----

def _now() -> datetime:
    return datetime.utcnow() + TIMEZONE


def _current_shift() -> dict | None:
    """根据当前时间匹配签到窗口(到岗 ~ 班次结束)"""
    now = _now()
    t = now.hour * 60 + now.minute
    for s in shifts():
        if s["arrive_m"] <= t < s["leave_m"]:
            return s
    return None


# ---- 数据库 ----

def _get_conn() -> sqlite3.Connection:
    dirname = os.path.dirname(DB_FILE)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    _init_db(conn)
    return conn


def _init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id    TEXT NOT NULL,
            user_id     TEXT NOT NULL,
            user_name   TEXT DEFAULT '',
            date        TEXT NOT NULL,
            period      TEXT NOT NULL,
            duration    INTEGER DEFAULT 0,
            time        TEXT
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_records_unique
            ON records(group_id, user_id, date, period)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_records_cleanup
            ON records(date)
    """)
    conn.commit()


def _cleanup(conn: sqlite3.Connection):
    if RETAIN_DAYS <= 0:
        return
    cutoff = (_now() - timedelta(days=RETAIN_DAYS)).strftime("%Y-%m-%d")
    conn.execute("DELETE FROM records WHERE date < ?", (cutoff,))
    conn.commit()


# ---- 签到(到岗即结算) ----

def checkin(group_id: str, user_id: str, user_name: str = "", hours: int | None = None) -> str:
    """到岗签到即结算时长。hours 来自消息 +N 后缀, 仅晚班需要。"""
    if not group_id or not user_id:
        return "参数错误。"

    shift = _current_shift()
    if shift is None:
        return "当前不在任何班次的签到时段内。"

    if shift["options"] is None:
        # 白班固定时长, 不接受 +N
        if hours is not None:
            return "白天班次无需带 +N, 直接发送「XX楼已到」即可。"
        credit = shift["hours"]
    else:
        # 晚班: 必须带 +N 且 N 在可选时长内
        if hours is None or hours not in shift["options"]:
            opts = sorted(shift["options"])
            return (
                f"晚班签到请带上时长后缀, 如「XX楼已到+{opts[0]}」(到21点) "
                f"或「XX楼已到+{opts[-1]}」(到22点)。"
            )
        credit = hours

    now = _now()
    today = now.strftime("%Y-%m-%d")

    conn = _get_conn()
    try:
        # INSERT OR IGNORE 依赖唯一索引, 保证每人每班次每天只结算一次
        cur = conn.execute(
            "INSERT OR IGNORE INTO records "
            "(group_id, user_id, user_name, date, period, duration, time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (group_id, user_id, user_name, today, shift["name"], credit, now.strftime(TM_FMT)),
        )
        if cur.rowcount == 0:
            return f"你今天「{shift['name']}」已经签到过了。"
        conn.commit()

        today_sum = _sum_duration(conn, group_id, user_id, today)
        total_sum = _sum_duration(conn, group_id, user_id)
        _cleanup(conn)
        return (
            f"签到成功! {shift['name']} +{_format_duration(credit)}\n"
            f"今日: {_format_duration(today_sum)}\n"
            f"累计: {_format_duration(total_sum)}"
        )
    finally:
        conn.close()


# ---- 补签 ----

def parse_shift(period: str) -> tuple[dict, int]:
    """解析补签的班次写法，返回 (班次, 录入时长)。

    固定班次直接写名字；带 options_hours 的班次必须写「晚班2」这种形式。
    """
    period = (period or "").strip()
    for s in shifts():
        if s["name"] != period:
            continue
        if s["options"]:
            opts = " / ".join(f"{s['name']}{n}" for n in s["options"])
            raise ValueError(f"「{s['name']}」请带上时长，如 {opts}")
        return s, s["hours"]

    m = re.fullmatch(r"(.+?)(\d+)", period)
    if m:
        for s in shifts():
            if s["name"] == m.group(1) and s["options"] and int(m.group(2)) in s["options"]:
                return s, int(m.group(2))
    raise ValueError("班次不存在，请参考补签说明里的班次格式。")


def _makeup_time(shift: dict) -> str:
    """在班次到岗后的随机窗口内取一个时间。"""
    cfg = load_feature_config("checkin")
    window = cfg.get("makeup_window_minutes", 15)
    try:
        window = max(0, int(window))
    except (TypeError, ValueError):
        window = 15

    start_m = shift["arrive_m"]
    end_m = min(start_m + window, shift["leave_m"])
    span = max(0, end_m - start_m) * 60
    seconds = start_m * 60 + (random.randrange(span) if span > 0 else 0)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def makeup(group_id: str, user_id: str, user_name: str, day: str, period: str) -> str:
    """补录一条签到记录。"""
    if not group_id or not user_id:
        return "参数错误。"

    shift, credit = parse_shift(period)
    record_time = _makeup_time(shift)

    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO records "
            "(group_id, user_id, user_name, date, period, duration, time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (group_id, user_id, user_name, day, shift["name"], credit, record_time),
        )
        if cur.rowcount == 0:
            row = conn.execute(
                "SELECT time FROM records "
                "WHERE group_id=? AND user_id=? AND date=? AND period=?",
                (group_id, user_id, day, shift["name"]),
            ).fetchone()
            when = f"（{row['time']}）" if row and row["time"] else ""
            return f"{user_name} 在 {day} 的「{shift['name']}」已有签到记录{when}，无需补签。"
        conn.commit()
        _cleanup(conn)
        return (
            f"补签成功：{day} {shift['name']} +{_format_duration(credit)}"
            f"（记录时间 {record_time}）\n"
            f"操作人：{user_name}"
        )
    finally:
        conn.close()


# ---- 内部辅助 ----

def _sum_duration(conn: sqlite3.Connection, group_id: str, user_id: str, date: str | None = None) -> int:
    sql = "SELECT COALESCE(SUM(duration), 0) FROM records WHERE group_id=? AND user_id=?"
    args: list = [group_id, user_id]
    if date:
        sql += " AND date=?"
        args.append(date)
    return conn.execute(sql, args).fetchone()[0]


def _format_duration(hours: int) -> str:
    return f"{hours}小时" if hours > 0 else "0小时"
