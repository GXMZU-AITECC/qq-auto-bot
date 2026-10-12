"""校历查询功能的单元测试。

覆盖四类判定分支：调休补班 / 放假区间 / 不在学期内 / 学期内周末与工作日。
判定逻辑走 judge(day, cfg)，不依赖真实配置文件，方便改写边界。
"""

import asyncio
from datetime import date

import pytest

from features.schoolcalendar import handler

BASE_CFG = {
    "enabled": True,
    "semester": {"name": "测试学期", "start": date(2026, 9, 7), "weeks": 20},
    "holidays": [{"from": date(2026, 10, 1), "to": date(2026, 10, 7), "name": "国庆节"}],
    "makeups": [
        {"date": date(2026, 10, 10), "name": "国庆调休补班", "for_weekday": "周四"}
    ],
}


def test_学期内的普通工作日上课():
    # 2026-09-08 周二，学期内、非假期、非周末
    assert handler.judge(date(2026, 9, 8), BASE_CFG) == ("上课", "正常教学日")


def test_学期内的周末放假():
    # 2026-09-12 周六
    status, reason = handler.judge(date(2026, 9, 12), BASE_CFG)
    assert status == "放假"
    assert reason == "周末"


def test_法定假期区间放假():
    # 2026-10-01 国庆
    assert handler.judge(date(2026, 10, 1), BASE_CFG) == ("放假", "国庆节")


def test_调休补班的周末算上课():
    # 2026-10-10 是周六，但配了调休补班 → 优先级高于周末
    assert handler.judge(date(2026, 10, 10), BASE_CFG) == (
        "上课",
        "国庆调休补班，上周四的课",
    )


def test_补班没写for_weekday时只给补班名():
    cfg = dict(BASE_CFG)
    cfg["makeups"] = [{"date": date(2026, 10, 10), "name": "国庆调休补班"}]
    assert handler.judge(date(2026, 10, 10), cfg) == ("上课", "国庆调休补班")


@pytest.mark.parametrize(
    "写法",
    ["周四", "星期四", "4", 4],
)
def test_for_weekday支持多种写法(写法):
    cfg = dict(BASE_CFG)
    cfg["makeups"] = [
        {"date": date(2026, 10, 10), "name": "国庆调休补班", "for_weekday": 写法}
    ]
    assert handler.judge(date(2026, 10, 10), cfg)[1].endswith("上周四的课")


def test_for_weekday写错时不影响补班判定():
    cfg = dict(BASE_CFG)
    cfg["makeups"] = [
        {"date": date(2026, 10, 10), "name": "国庆调休补班", "for_weekday": "周八"}
    ]
    status, reason = handler.judge(date(2026, 10, 10), cfg)
    assert status == "上课"
    assert "周几" not in reason


def test_学期区间外不算上课():
    # 2026-08-01 早于学期开始
    assert handler.judge(date(2026, 8, 1), BASE_CFG) == ("不在学期内", "")


def test_超出学期总周数也不算上课():
    # 20 周 = 140 天，2026-09-07 起，最后一天是 2027-01-24
    assert handler.judge(date(2027, 2, 1), BASE_CFG) == ("不在学期内", "")


def test_教学周次从第一周开始算():
    info = handler.semester_info(date(2026, 9, 8), BASE_CFG)
    assert info["week"] == 1
    info = handler.semester_info(date(2026, 9, 14), BASE_CFG)
    assert info["week"] == 2


def test_学期配置缺失时返回空():
    assert handler.semester_info(date(2026, 9, 8), {"enabled": True}) is None


def test_日期写成字符串也能解析():
    cfg = dict(BASE_CFG)
    cfg["semester"] = {"name": "字符串学期", "start": "2026/09/07", "weeks": 20}
    assert handler.semester_info(date(2026, 9, 8), cfg)["week"] == 1


def test_坏日期不会被当成有效条目():
    cfg = dict(BASE_CFG)
    cfg["makeups"] = [{"date": "不是日期", "name": "坏数据"}]
    # 坏条目跳过，这天仍是普通的学期内周日
    assert handler.judge(date(2026, 9, 13), cfg) == ("放假", "周末")


def test_未启用时命令不回复(monkeypatch):
    monkeypatch.setattr(handler, "load_feature_config", lambda name: {"enabled": False})
    assert asyncio.run(handler.cmd_calendar(None, "1", "2", "校历")) is None


def test_校历命令给出状态与周次(monkeypatch):
    monkeypatch.setattr(handler, "load_feature_config", lambda name: BASE_CFG)
    out = asyncio.run(handler.cmd_calendar(None, "1", "2", "校历"))
    assert "·" in out
    assert "测试学期" in out


def test_调休命令列出补班日期与补周几(monkeypatch):
    monkeypatch.setattr(handler, "load_feature_config", lambda name: BASE_CFG)
    out = asyncio.run(handler.cmd_makeups(None, "1", "2", "调休"))
    assert "2026-10-10" in out
    assert "国庆调休补班" in out
    assert "上周四的课" in out


def test_没有调休时给出空提示(monkeypatch):
    cfg = dict(BASE_CFG)
    cfg["makeups"] = []
    monkeypatch.setattr(handler, "load_feature_config", lambda name: cfg)
    out = asyncio.run(handler.cmd_makeups(None, "1", "2", "调休"))
    assert "没有配置" in out


def test_校历没配好时不把配置路径发到群里(monkeypatch, caplog):
    """配置缺失是维护者的事：只进后台日志，群友不该看到内部路径。"""
    cfg = {"enabled": True}  # 故意不给 semester
    monkeypatch.setattr(handler, "load_feature_config", lambda name: cfg)
    with caplog.at_level("WARNING", logger="features.schoolcalendar"):
        out = asyncio.run(handler.cmd_calendar(None, "1", "2", "校历"))
    assert "configs/schoolcalendar.yaml" not in out  # 回复里没有内部路径
    assert any("semester.start" in r.message for r in caplog.records)  # 进了日志


@pytest.mark.parametrize(
    ("问法", "期望偏移"),
    [("今天上课吗", 0), ("明天有课吗", 1), ("后天上课吗？", 2)],
)
def test_自然语言问法按天偏移(monkeypatch, 问法, 期望偏移):
    monkeypatch.setattr(handler, "load_feature_config", lambda name: BASE_CFG)
    out = asyncio.run(handler.cmd_ask(None, "1", "2", 问法))
    目标日 = date.today().toordinal() + 期望偏移
    assert date.fromordinal(目标日).isoformat() in out


def test_导出了命令与正则():
    assert "校历" in handler.COMMANDS
    assert "调休" in handler.COMMANDS
    assert handler.COMMAND_PATTERNS


def test_命令名不带斜杠():
    """与 demo(烤肠) / easteregg(我们会赢吗) 的现有指令风格保持一致。"""
    for cmd in handler.COMMANDS:
        assert not cmd.startswith("/"), f"命令 {cmd!r} 不应带斜杠"
