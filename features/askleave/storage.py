"""请假记录存储。

与签到功能共用 config.yaml 里 data.file 指向的 SQLite 库，只是用独立的 leaves 表，
既不引入第二份数据库配置，也不会和签到的数据混在一起。

同一人同一天同一班次只记一条（唯一索引），重复登记的 INSERT 会被忽略。
"""

import os
import sqlite3
from datetime import datetime, timedelta

from config import get

TIMEZONE = timedelta(hours=8)
DB_FILE = get("data", "file", default="data/checkin_data.db")
RETAIN_DAYS = get("data", "retain_days", default=0)


def _now() -> datetime:
    return datetime.utcnow() + TIMEZONE


def _conn() -> sqlite3.Connection:
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
        CREATE TABLE IF NOT EXISTS leaves (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id  TEXT NOT NULL,
            user_id   TEXT NOT NULL,
            user_name TEXT DEFAULT '',
            date      TEXT NOT NULL,
            period    TEXT NOT NULL,
            reason    TEXT DEFAULT '',
            time      TEXT
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_leaves_unique
            ON leaves(group_id, user_id, date, period)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_leaves_cleanup
            ON leaves(date)
    """)
    conn.commit()


def _cleanup(conn: sqlite3.Connection):
    if RETAIN_DAYS <= 0:
        return
    cutoff = (_now() - timedelta(days=RETAIN_DAYS)).strftime("%Y-%m-%d")
    conn.execute("DELETE FROM leaves WHERE date < ?", (cutoff,))
    conn.commit()


# ---- 写 ----

def add(group_id: str, user_id: str, user_name: str, day: str, period: str, reason: str = "") -> bool:
    """登记一条请假。返回 True 表示新增，False 表示这条已经登记过。"""
    now = _now()
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO leaves "
            "(group_id, user_id, user_name, date, period, reason, time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(group_id), str(user_id), user_name or "", day, period, reason or "",
             now.strftime("%H:%M:%S")),
        )
        conn.commit()
        if cur.rowcount > 0:
            _cleanup(conn)
            return True
        return False
    finally:
        conn.close()


def remove(group_id: str, user_id: str, day: str, period: str | None = None) -> int:
    """取消请假。period 为 None 时取消当天全部班次，返回删除条数。"""
    sql = "DELETE FROM leaves WHERE group_id=? AND user_id=? AND date=?"
    args: list = [str(group_id), str(user_id), day]
    if period:
        sql += " AND period=?"
        args.append(period)
    conn = _conn()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---- 读 ----

def list_by_date(group_id: str, day: str) -> list[dict]:
    """某群某天的全部请假记录。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM leaves WHERE group_id=? AND date=? ORDER BY period, user_name",
            (str(group_id), day),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_user_by_date(group_id: str, user_id: str, day: str) -> list[dict]:
    """某人在某群某天的请假记录。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM leaves WHERE group_id=? AND user_id=? AND date=? ORDER BY period",
            (str(group_id), str(user_id), day),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_by_period(group_id: str, day: str, period: str) -> list[dict]:
    """某群某天某个班次的请假记录，用于到点提醒。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM leaves WHERE group_id=? AND date=? AND period=? ORDER BY user_name",
            (str(group_id), day, period),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def groups_with_leave(day: str, period: str) -> list[str]:
    """哪些群在这个班次有请假的人 —— 提醒要按群分别发。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT group_id FROM leaves WHERE date=? AND period=?",
            (day, period),
        ).fetchall()
        return [r["group_id"] for r in rows]
    finally:
        conn.close()
