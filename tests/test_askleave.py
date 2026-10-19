"""请假功能的单元测试。

存储层用临时 SQLite（monkeypatch storage.DB_FILE），不碰真实的 data/checkin_data.db；
配置与 bot 对象都用替身，测试不依赖真实环境和网络。
"""

import asyncio
from datetime import date, datetime, timedelta

import pytest

from features.askleave import handler, storage

CHECKIN_CFG = {
    "checkin_shifts": [
        {"name": "一班次", "arrive": "07:40", "leave": "09:20", "duration_hours": 2},
        {"name": "二班次", "arrive": "09:50", "leave": "12:20", "duration_hours": 3},
        {"name": "三班次", "arrive": "14:10", "leave": "15:50", "duration_hours": 2},
        {"name": "四班次", "arrive": "16:20", "leave": "18:00", "duration_hours": 2},
        {"name": "晚班", "arrive": "19:20", "leave": "22:00", "options_hours": [2, 3]},
    ]
}
ASKLEAVE_CFG = {"enabled": True, "notify_before_minutes": 30}


class FakeBot:
    """替身 bot：记录发出去的消息，昵称固定。"""

    def __init__(self, name="张三"):
        self.name = name
        self.sent: list[tuple[str, str]] = []

    async def get_group_member_name(self, group_id, user_id):
        return self.name

    async def send_group_msg(self, group_id, text):
        self.sent.append((str(group_id), text))


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    """所有用例共用：隔离数据库 + 固定配置。"""
    monkeypatch.setattr(storage, "DB_FILE", str(tmp_path / "test.db"))

    def fake_cfg(name):
        return {"checkin": CHECKIN_CFG, "askleave": ASKLEAVE_CFG}.get(name, {})

    monkeypatch.setattr(handler, "load_feature_config", fake_cfg)


# ------------------------------------------------------------ 解析

@pytest.mark.parametrize(
    ("消息", "期望班次", "期望原因"),
    [
        ("请假 一班次", ["一班次"], ""),
        ("请假一班次", ["一班次"], ""),
        ("请假 一班次 去医院", ["一班次"], "去医院"),
        ("请假 一班次 二班次", ["一班次", "二班次"], ""),
        ("请假 明天 晚班 家里有事", ["晚班"], "家里有事"),
        ("请假 今天 三班次", ["三班次"], ""),
        ("请假 1班次", ["一班次"], ""),          # 数字简写
        ("请假 2班", ["二班次"], ""),
        ("请假 晚自修", ["晚班"], ""),            # 前缀简写
    ],
)
def test_解析各种请假写法(消息, 期望班次, 期望原因):
    day, periods, reason, err = handler.parse_leave(消息, CHECKIN_CFG)
    assert err == "", f"不该报错: {err}"
    assert periods == 期望班次
    assert reason == 期望原因
    assert day is not None


def test_没写班次时给可用班次清单():
    _, periods, _, err = handler.parse_leave("请假 明天", CHECKIN_CFG)
    assert periods == []
    assert "没认出班次" in err
    assert "一班次" in err


def test_乱填的班次名会被忽略而不是崩掉():
    _, periods, reason, err = handler.parse_leave("请假 五班次", CHECKIN_CFG)
    assert err
    assert periods == []


def test_班次未配置时提示维护者():
    _, _, _, err = handler.parse_leave("请假 一班次", {})
    assert "checkin_shifts" in err


@pytest.mark.parametrize(
    ("词", "期望偏移"),
    [("今天", 0), ("明天", 1), ("后天", 2)],
)
def test_日期词按天偏移(词, 期望偏移):
    assert handler._parse_day(词) == handler._today() + timedelta(days=期望偏移)


def test_月日格式按当前年份解析():
    目标 = handler._parse_day("10-20")
    assert 目标.month == 10 and 目标.day == 20
    assert 目标.year == handler._today().year


def test_完整日期原样解析():
    assert handler._parse_day("2026-10-20") == date(2026, 10, 20)


def test_非法日期返回None():
    assert handler._parse_day("不是日期") is None
    assert handler._parse_day("2026-13-45") is None


# ------------------------------------------------------------ 登记 / 取消 / 名单

def test_请假登记并回复确认(monkeypatch):
    monkeypatch.setattr(storage, "add", lambda *a, **k: True)
    out = asyncio.run(handler.ask_leave(FakeBot(), "100", "9001", "请假 一班次 去医院"))
    assert "已登记" in out
    assert "张三" in out
    assert "一班次" in out
    assert "07:40" in out          # 带上到岗时间
    assert "去医院" in out


def test_同一天同一班次重复登记会提示(monkeypatch):
    monkeypatch.setattr(storage, "add", lambda *a, **k: False)
    out = asyncio.run(handler.ask_leave(FakeBot(), "100", "9001", "请假 一班次"))
    assert "已经登记过" in out


def test_多个班次部分重复时分开说明(monkeypatch):
    能否登记 = {"一班次": True, "二班次": False}
    monkeypatch.setattr(
        storage, "add", lambda gid, uid, name, day, period, reason: 能否登记[period]
    )
    out = asyncio.run(handler.ask_leave(FakeBot(), "100", "9001", "请假 一班次 二班次"))
    assert "一班次" in out and "二班次" in out
    assert "之前已经登记过" in out


def test_未启用时静默(monkeypatch):
    monkeypatch.setattr(handler, "load_feature_config", lambda name: {"enabled": False})
    assert asyncio.run(handler.ask_leave(FakeBot(), "100", "9001", "请假 一班次")) is None
    assert asyncio.run(handler.leave_list(FakeBot(), "100", "9001", "请假名单")) is None


def test_取消请假(monkeypatch):
    monkeypatch.setattr(
        storage, "list_user_by_date",
        lambda gid, uid, day: [{"period": "一班次"}, {"period": "二班次"}],
    )
    monkeypatch.setattr(storage, "remove", lambda *a: 1)
    out = asyncio.run(handler.cancel_leave(FakeBot(), "100", "9001", "取消请假 一班次"))
    assert "已取消" in out
    assert "一班次" in out
    assert "二班次" not in out     # 只取消指定的班次


def test_取消全部班次(monkeypatch):
    monkeypatch.setattr(
        storage, "list_user_by_date",
        lambda gid, uid, day: [{"period": "一班次"}, {"period": "二班次"}],
    )
    monkeypatch.setattr(storage, "remove", lambda *a: 1)
    out = asyncio.run(handler.cancel_leave(FakeBot(), "100", "9001", "取消请假"))
    assert "一班次" in out and "二班次" in out


def test_取消没有记录时说明情况(monkeypatch):
    monkeypatch.setattr(storage, "list_user_by_date", lambda gid, uid, day: [])
    out = asyncio.run(handler.cancel_leave(FakeBot(), "100", "9001", "取消请假 一班次"))
    assert "没查到" in out


def test_请假名单按班次列出(monkeypatch):
    monkeypatch.setattr(
        storage, "list_by_date",
        lambda gid, day: [
            {"user_name": "张三", "user_id": "1", "period": "一班次", "reason": "去医院"},
            {"user_name": "李四", "user_id": "2", "period": "晚班", "reason": ""},
        ],
    )
    out = asyncio.run(handler.leave_list(FakeBot(), "100", "9001", "请假名单"))
    assert "请假名单" in out
    assert "张三 一班次（去医院）" in out
    assert "李四 晚班" in out


def test_没人请假时名单给空提示(monkeypatch):
    monkeypatch.setattr(storage, "list_by_date", lambda gid, day: [])
    out = asyncio.run(handler.leave_list(FakeBot(), "100", "9001", "请假名单"))
    assert "没有人请假" in out


def test_明天名单按明天日期查询(monkeypatch):
    查询日 = []
    monkeypatch.setattr(
        storage, "list_by_date",
        lambda gid, day: 查询日.append(day) or [],
    )
    asyncio.run(handler.leave_list(FakeBot(), "100", "9001", "请假名单 明天"))
    assert 查询日[0] == (handler._today() + timedelta(days=1)).isoformat()


# ------------------------------------------------------------ 提醒

def test_班次到岗前30分钟触发提醒():
    到点 = datetime(2026, 10, 20, 7, 10)     # 一班次 07:40 - 30min
    due = handler.due_shifts(到点, ASKLEAVE_CFG, "2026-10-20")
    assert [s["name"] for s in due] == ["一班次"]


@pytest.mark.parametrize(
    ("时刻", "是否触发"),
    [(datetime(2026, 10, 20, 7, 9), False), (datetime(2026, 10, 20, 7, 11), False)],
)
def test_非提醒时刻不触发(时刻, 是否触发):
    assert handler.due_shifts(时刻, ASKLEAVE_CFG, "2026-10-20") == []


def test_晚班提醒时刻():
    due = handler.due_shifts(datetime(2026, 10, 20, 18, 50), ASKLEAVE_CFG, "2026-10-20")
    assert [s["name"] for s in due] == ["晚班"]


def test_提醒文案含班次时间与人名原因():
    班次 = {"name": "一班次", "arrive": "07:40", "arrive_m": 460}
    文本 = handler.notify_text(
        班次,
        [
            {"user_name": "张三", "user_id": "1", "reason": "去医院"},
            {"user_name": "李四", "user_id": "2", "reason": ""},
        ],
        30,
    )
    assert "一班次" in 文本 and "30 分钟" in 文本 and "07:40" in 文本
    assert "张三（去医院）" in 文本
    assert "李四" in 文本
    assert "@" not in 文本          # 按约定只列名单，不 @


def test_提醒只发给有请假记录的群(monkeypatch):
    monkeypatch.setattr(storage, "groups_with_leave", lambda day, period: ["100", "200"])
    monkeypatch.setattr(
        storage, "list_by_period",
        lambda gid, day, period: [{"user_name": "张三", "user_id": "1", "reason": ""}]
        if gid == "100" else [],
    )
    bot = FakeBot()
    班次 = {"name": "一班次", "arrive": "07:40", "arrive_m": 460}
    asyncio.run(handler.tick_once(bot, datetime(2026, 10, 20, 7, 10), 班次))
    assert [g for g, _ in bot.sent] == ["100"]     # 200 群没记录，不该被打扰


def test_没人请假时不发提醒(monkeypatch):
    monkeypatch.setattr(storage, "groups_with_leave", lambda day, period: [])
    bot = FakeBot()
    班次 = {"name": "一班次", "arrive": "07:40", "arrive_m": 460}
    asyncio.run(handler.tick_once(bot, datetime(2026, 10, 20, 7, 10), 班次))
    assert bot.sent == []


# ------------------------------------------------------------ 存储（真 SQLite）

def test_同一人同班次重复登记只有一条():
    今天 = handler._today().isoformat()
    assert storage.add("100", "9001", "张三", 今天, "一班次", "去医院") is True
    assert storage.add("100", "9001", "张三", 今天, "一班次", "换个理由") is False
    全部 = storage.list_by_date("100", 今天)
    assert len(全部) == 1
    assert 全部[0]["reason"] == "去医院"      # 重复登记不覆盖原因


def test_不同人可以请同一个班次():
    今天 = handler._today().isoformat()
    storage.add("100", "9001", "张三", 今天, "一班次")
    storage.add("100", "9002", "李四", 今天, "一班次")
    assert len(storage.list_by_period("100", 今天, "一班次")) == 2


def test_按群隔离互不干扰():
    今天 = handler._today().isoformat()
    storage.add("100", "9001", "张三", 今天, "一班次")
    storage.add("200", "9002", "李四", 今天, "一班次")
    assert len(storage.list_by_date("100", 今天)) == 1
    assert len(storage.list_by_date("200", 今天)) == 1


def test_取消指定班次只删那一条():
    今天 = handler._today().isoformat()
    storage.add("100", "9001", "张三", 今天, "一班次")
    storage.add("100", "9001", "张三", 今天, "二班次")
    assert storage.remove("100", "9001", 今天, "一班次") == 1
    assert [r["period"] for r in storage.list_user_by_date("100", "9001", 今天)] == ["二班次"]


def test_取消不带班次则清空当天():
    今天 = handler._today().isoformat()
    storage.add("100", "9001", "张三", 今天, "一班次")
    storage.add("100", "9001", "张三", 今天, "二班次")
    assert storage.remove("100", "9001", 今天) == 2
    assert storage.list_user_by_date("100", "9001", 今天) == []


def test_groups_with_leave只返回有记录的群():
    今天 = handler._today().isoformat()
    storage.add("100", "9001", "张三", 今天, "一班次")
    storage.add("300", "9003", "王五", 今天, "一班次")
    assert sorted(storage.groups_with_leave(今天, "一班次")) == ["100", "300"]
    assert storage.groups_with_leave(今天, "晚班") == []


# ------------------------------------------------------------ 路由约定

def test_命令名不带斜杠():
    for pat in handler.COMMAND_PATTERNS:
        assert not pat.startswith("/"), f"命令 {pat!r} 不应带斜杠"


def test_导出了STARTUP后台任务():
    assert handler.STARTUP
    assert asyncio.iscoroutinefunction(handler.STARTUP[0])


def test_消息按注册顺序路由到正确的处理函数(monkeypatch):
    """dict 有序 —— 名单/取消排在「请假」前面，否则会被它吃掉。端到端验证。"""
    import features

    async def 说名单(bot, gid, uid, text):
        return "命中:名单"

    async def 说取消(bot, gid, uid, text):
        return "命中:取消"

    async def 说请假(bot, gid, uid, text):
        return "命中:请假"

    正则们 = list(handler.COMMAND_PATTERNS)
    monkeypatch.setattr(handler, "COMMAND_PATTERNS", {
        正则们[0]: 说名单,
        正则们[1]: 说取消,
        正则们[2]: 说请假,
    })
    features.discover()

    async def 派发(text):
        return await features.dispatch(FakeBot(), "100", "9001", text)

    assert asyncio.run(派发("请假名单")) == "命中:名单"
    assert asyncio.run(派发("请假名单 明天")) == "命中:名单"
    assert asyncio.run(派发("取消请假 一班次")) == "命中:取消"
    assert asyncio.run(派发("请假 一班次")) == "命中:请假"
    assert asyncio.run(派发("请假 明天 晚班 有事")) == "命中:请假"
