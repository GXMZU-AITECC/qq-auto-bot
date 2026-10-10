"""节假日日历：判断某天是否工作日（含调休），带磁盘缓存与按需刷新。

来源 payload 经 _parse_days 归一为 {date_str: isOffDay}：
- timor.tech: {"holiday": {"MM-DD": {"holiday": bool, "date": "YYYY-MM-DD"}}}
- apihubs:    {"data": {"list": [{"date": 20261010, "workday": 1|2}]}}
无该年数据时 is_workday 返回 None（未知），由上层决定兜底策略。
"""

import json
import os
from datetime import date

import httpx

from config import get, load_feature_config

_DEFAULT_SOURCES = [
    "https://timor.tech/api/holiday/year/{year}/",
    "https://api.apihubs.cn/holiday/get?year={year}&size=400",
]

_mem: dict[int, dict[str, bool]] = {}  # year -> {date_str: isOffDay}


def is_workday(d: date) -> bool | None:
    """True=工作日(含调休补班), False=休息日, None=未知(无数据)。"""
    table = _table(d.year)
    if table is None:
        return None
    key = d.isoformat()
    if key in table:
        return not table[key]  # isOffDay=True 表示休息
    return d.weekday() < 5  # 普通日：周一到五为工作日


async def ensure(year: int) -> None:
    """仅在缺该年数据时拉取并写缓存；已有有效缓存则直接返回。"""
    if _table(year) is not None:
        return
    for tpl in _sources():
        payload = await _fetch(tpl.format(year=year))
        table = _parse_days(payload, year)
        if table:
            _write_cache(year, table)
            _mem[year] = table
            return


def _sources() -> list[str]:
    cfg = load_feature_config("scheduled")
    srcs = cfg.get("calendar_sources")
    return list(srcs) if srcs else list(_DEFAULT_SOURCES)


def _table(year: int) -> dict[str, bool] | None:
    table = _mem.get(year)
    if table is not None:
        return table
    table = _load_cache(year)
    if table is not None:
        _mem[year] = table
    return table


def _cache_path(year: int) -> str:
    base = get("data", "calendar_dir", default="data/calendar")
    return os.path.join(base, f"{year}.json")


def _load_cache(year: int) -> dict[str, bool] | None:
    path = _cache_path(year)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("year") != year:
        return None
    days = data.get("days")
    if not isinstance(days, dict) or not days:
        return None
    return {str(k): bool(v) for k, v in days.items()}


def _write_cache(year: int, table: dict[str, bool]) -> None:
    path = _cache_path(year)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"year": year, "days": table}, f, ensure_ascii=False)
    except OSError:
        pass


async def _fetch(url: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def _parse_days(payload, year: int) -> dict[str, bool] | None:
    """归一为 {date_str: isOffDay}；未发布/空数据返回 None。"""
    if not isinstance(payload, dict):
        return None
    days = payload.get("holiday")  # timor：仅列特殊日
    if isinstance(days, dict):
        return _parse_timor(days, year)
    data = payload.get("data")  # apihubs：全年每日
    if isinstance(data, dict) and isinstance(data.get("list"), list):
        return _parse_apihubs(data["list"], year)
    return None


def _parse_timor(days: dict, year: int) -> dict[str, bool] | None:
    table: dict[str, bool] = {}
    for key, item in days.items():
        if not isinstance(item, dict) or "holiday" not in item:
            continue
        ds = item.get("date") or f"{year}-{key}"
        table[ds] = bool(item["holiday"])  # holiday=True 表示放假(休息)
    return _filter_year(table, year)


def _parse_apihubs(items: list, year: int) -> dict[str, bool] | None:
    table: dict[str, bool] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        raw, wd = item.get("date"), item.get("workday")
        if raw is None or wd not in (1, 2):
            continue
        s = str(raw)
        ds = f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s
        table[ds] = wd != 1  # workday=1 为工作日
    return _filter_year(table, year)


def _filter_year(table: dict[str, bool], year: int) -> dict[str, bool] | None:
    prefix = f"{year}-"
    table = {k: v for k, v in table.items() if k.startswith(prefix)}
    return table or None
