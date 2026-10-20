"""戳一戳功能：触发逻辑单测（不连 QQ，用假 bot + 假配置）。"""

import asyncio

import pytest

import features
import features.poke.handler as poke
from features.poke.handler import handle_poke


class FakeBot:
    """假机器人：只记录被调用了哪些 API，不发真请求"""

    def __init__(self):
        self.calls = []

    async def _api_call(self, action, params):
        self.calls.append((action, params))
        return {"status": "ok"}

    async def group_poke(self, group_id, user_id):
        await self._api_call("group_poke", {"group_id": int(group_id), "user_id": int(user_id)})


def _cfg(**over) -> dict:
    """一份测试用配置，可用关键字覆盖任意字段"""
    base = {
        "enabled": True,
        "poke_back_chance": 0.3,
        "replies": ["回话1", "回话2", "回话3", "回话4", "回话5"],
        "spam_window_seconds": 60,
        "spam_threshold": 15,
        "spam_cooldown_seconds": 30,
        "spam_reply": "被戳死了……30 秒后复活",
    }
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def _clean_state():
    """每个用例前清空模块级状态，避免互相影响"""
    poke._recent.clear()
    poke._cooldown_until.clear()
    poke._warned.clear()
    yield


def _patch(monkeypatch, **over) -> dict:
    """把 load_feature_config 换成返回测试配置"""
    cfg = _cfg(**over)
    monkeypatch.setattr(poke, "load_feature_config", lambda name: cfg)
    return cfg


def _freeze_time(monkeypatch, start: float = 0.0) -> dict:
    """把 time.monotonic 换成手动可控的时钟，返回 {"t": 秒数} 供测试推进"""
    clock = {"t": start}
    monkeypatch.setattr(poke.time, "monotonic", lambda: clock["t"])
    return clock


def test_导出了_POKE_HANDLERS():
    assert handle_poke in poke.POKE_HANDLERS


def test_discover_能收走_poke_处理器():
    features.discover()
    assert handle_poke in features._poke_handlers


def test_未启用时静默(monkeypatch):
    _patch(monkeypatch, enabled=False)
    bot = FakeBot()
    assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None
    assert bot.calls == []


def test_骰子命中反戳区间时反戳且不回话(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(poke.random, "random", lambda: 0.0)  # 0.0 < 0.3 → 反戳
    bot = FakeBot()
    reply = asyncio.run(handle_poke(bot, "111", "222", "333"))
    assert bot.calls == [("group_poke", {"group_id": 111, "user_id": 222})]
    assert reply is None


def test_骰子落在回复区间时回话且不反戳(monkeypatch):
    cfg = _patch(monkeypatch)
    monkeypatch.setattr(poke.random, "random", lambda: 0.3)  # 0.3 不小于 0.3 → 回话
    bot = FakeBot()
    reply = asyncio.run(handle_poke(bot, "111", "222", "333"))
    assert bot.calls == []
    assert reply in cfg["replies"]


def test_反戳与回话互斥且每次必有反应(monkeypatch):
    _patch(monkeypatch)
    for r in (0.0, 0.29, 0.3, 0.99):
        bot = FakeBot()
        monkeypatch.setattr(poke.random, "random", lambda r=r: r)
        reply = asyncio.run(handle_poke(bot, "111", "222", "333"))
        assert reply is not None or bot.calls  # 要么回话，要么反戳


def test_一分钟内戳满阈值被戳死并静默(monkeypatch):
    cfg = _patch(monkeypatch, spam_threshold=3)
    monkeypatch.setattr(poke.random, "random", lambda: 0.0)  # 正常路径走反戳
    bot = FakeBot()
    _freeze_time(monkeypatch)

    for _ in range(2):  # 前 2 次没到阈值，走正常路径
        assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None
    # 第 3 次达到阈值 → 被戳死
    assert asyncio.run(handle_poke(bot, "111", "222", "333")) == cfg["spam_reply"]
    # 倒地期间：完全静默，也不反戳
    calls_before = len(bot.calls)
    assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None
    assert len(bot.calls) == calls_before


def test_超过窗口的戳不计入(monkeypatch):
    _patch(monkeypatch, spam_threshold=3, spam_window_seconds=60)
    monkeypatch.setattr(poke.random, "random", lambda: 0.0)  # 走反戳，返回 None
    bot = FakeBot()
    clock = _freeze_time(monkeypatch)

    assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None  # t=0
    clock["t"] = 30
    assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None  # t=30
    clock["t"] = 61
    # t=0 那次已超出 60 秒窗口被清掉，窗口内只剩 2 次 → 不触发戳死
    assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None


def test_冷却结束后复活(monkeypatch):
    cfg = _patch(monkeypatch, spam_threshold=2, spam_cooldown_seconds=30)
    monkeypatch.setattr(poke.random, "random", lambda: 0.0)
    bot = FakeBot()
    clock = _freeze_time(monkeypatch)

    assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None  # 第 1 次
    assert asyncio.run(handle_poke(bot, "111", "222", "333")) == cfg["spam_reply"]  # 第 2 次戳死

    calls_before = len(bot.calls)
    clock["t"] = 10  # 倒地中
    assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None
    assert len(bot.calls) == calls_before

    clock["t"] = 31  # 冷却结束 → 复活，恢复反戳
    assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None
    assert len(bot.calls) == calls_before + 1


def test_处理器抛异常时不把报错发到群里(monkeypatch):
    """notice 事件出错只能记日志，不能把异常文案当回复发进群"""

    async def boom(bot, group_id, user_id, target_id):
        raise RuntimeError("炸了")

    monkeypatch.setattr(features, "_poke_handlers", [boom])
    bot = FakeBot()
    assert asyncio.run(features.dispatch_poke(bot, "111", "222", "333")) is None
    assert bot.calls == []


def test_不同人戳也累计到同一个群计数(monkeypatch):
    """按群计数：甲戳 1 次 + 乙戳 1 次 = 2 次，够阈值就戳死（全群连坐）"""
    cfg = _patch(monkeypatch, spam_threshold=2)
    monkeypatch.setattr(poke.random, "random", lambda: 0.0)  # 走反戳，返回 None
    bot = FakeBot()
    _freeze_time(monkeypatch)

    assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None  # 甲第 1 次
    assert asyncio.run(handle_poke(bot, "111", "999", "333")) == cfg["spam_reply"]  # 乙第 2 次 → 戳死


def test_不同群互不影响(monkeypatch):
    """111 群被戳死，222 群照常反应"""
    cfg = _patch(monkeypatch, spam_threshold=2)
    monkeypatch.setattr(poke.random, "random", lambda: 0.0)  # 走反戳，返回 None
    bot = FakeBot()
    _freeze_time(monkeypatch)

    assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None  # 111 群第 1 次
    assert asyncio.run(handle_poke(bot, "111", "222", "333")) == cfg["spam_reply"]  # 第 2 次戳死
    # 222 群计数独立，仍是第 1 次 → 正常反戳
    calls_before = len(bot.calls)
    assert asyncio.run(handle_poke(bot, "222", "222", "333")) is None
    assert len(bot.calls) == calls_before + 1


def test_安全读数字_非法值回退默认值():
    """配置写错不该让功能静默失效，而是回退默认值"""
    assert poke._cfg_number({"x": "很多"}, "x", 15, int, minimum=1) == 15  # 不是数字
    assert poke._cfg_number({"x": None}, "x", 15, int, minimum=1) == 15  # 空值
    assert poke._cfg_number({"x": -1}, "x", 15, int, minimum=1) == 15  # 小于下限
    assert poke._cfg_number({"x": 1.5}, "x", 0.3, float, maximum=1.0) == 0.3  # 概率超 1
    assert poke._cfg_number({"x": "3"}, "x", 15, int, minimum=1) == 3  # 字符串数字仍可用
    assert poke._cfg_number({}, "x", 60.0, float) == 60.0  # 缺字段用默认值


def test_阈值配错时按默认值继续工作(monkeypatch, caplog):
    """spam_threshold 写成非数字 → 回退 15，仍然第 15 次戳死，并留下 warning"""
    cfg = _patch(monkeypatch, spam_threshold="很多")
    monkeypatch.setattr(poke.random, "random", lambda: 0.0)  # 走反戳，返回 None
    bot = FakeBot()
    _freeze_time(monkeypatch)

    with caplog.at_level("WARNING", logger="features.poke"):
        for _ in range(14):
            assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None
        assert asyncio.run(handle_poke(bot, "111", "222", "333")) == cfg["spam_reply"]

    assert "spam_threshold" in caplog.text


def test_戳死台词里的秒数跟配置走(monkeypatch):
    """spam_reply 用 {seconds} 占位，改冷却时间不用再手改文案"""
    _patch(
        monkeypatch,
        spam_threshold=1,
        spam_cooldown_seconds=5,
        spam_reply="被戳死了……{seconds} 秒后复活",
    )
    bot = FakeBot()
    _freeze_time(monkeypatch)

    assert asyncio.run(handle_poke(bot, "111", "222", "333")) == "被戳死了……5 秒后复活"


def test_戳死台词占位符写错时原样发送(monkeypatch):
    """模板里写了不认识的占位符，不能让戳死这条路径抛异常"""
    _patch(monkeypatch, spam_threshold=1, spam_reply="被戳死了……{second} 秒后复活")
    bot = FakeBot()
    _freeze_time(monkeypatch)

    assert asyncio.run(handle_poke(bot, "111", "222", "333")) == "被戳死了……{second} 秒后复活"


def test_戳死台词属性访问写错时原样发送(monkeypatch):
    """{seconds.foo} / {seconds[0]} 会抛 AttributeError / TypeError，同样要兜住"""
    templates = ["被戳死了……{seconds.foo} 秒后复活", "被戳死了……{seconds[0]} 秒后复活"]
    for i, tpl in enumerate(templates):
        _patch(monkeypatch, spam_threshold=1, spam_reply=tpl)
        bot = FakeBot()
        _freeze_time(monkeypatch)
        # 每个模板用不同群号，避免上一轮的冷却影响这一轮
        assert asyncio.run(handle_poke(bot, str(100 + i), "222", "333")) == tpl


def test_配置写错只提示一次(monkeypatch, caplog):
    """每次被戳都会重新读配置，但同一个错值只该 warning 一次，避免刷日志"""
    _patch(monkeypatch, spam_threshold="很多")
    monkeypatch.setattr(poke.random, "random", lambda: 0.0)
    bot = FakeBot()
    _freeze_time(monkeypatch)

    with caplog.at_level("WARNING", logger="features.poke"):
        for _ in range(3):
            asyncio.run(handle_poke(bot, "111", "222", "333"))

    assert caplog.text.count("spam_threshold") == 1


def test_冷却结束的群会被清理(monkeypatch):
    """倒地结束后该群状态应被清掉，字典不随群数无限增长"""
    _patch(monkeypatch, spam_threshold=1, spam_cooldown_seconds=5)
    bot = FakeBot()
    clock = _freeze_time(monkeypatch)

    asyncio.run(handle_poke(bot, "111", "222", "333"))  # 111 群戳死
    assert "111" in poke._recent and "111" in poke._cooldown_until

    clock["t"] = 100
    asyncio.run(handle_poke(bot, "222", "222", "333"))  # 另一个群被戳时顺手清理
    assert "111" not in poke._recent
    assert "111" not in poke._cooldown_until


def test_窗口内已无记录的群会被清理(monkeypatch):
    """只有历史时间戳、早就滑出窗口的群也要清掉"""
    _patch(monkeypatch, spam_threshold=99)
    monkeypatch.setattr(poke.random, "random", lambda: 0.0)
    bot = FakeBot()
    clock = _freeze_time(monkeypatch)

    asyncio.run(handle_poke(bot, "111", "222", "333"))
    assert poke._recent["111"]

    clock["t"] = 200  # 远超 60 秒窗口
    asyncio.run(handle_poke(bot, "222", "222", "333"))
    assert "111" not in poke._recent

def test_replies_写成字符串时忽略并提示(monkeypatch, caplog):
    """replies 本该是列表，写成字符串时不能返回单个字"""
    _patch(monkeypatch, poke_back_chance=0.0, replies="别戳了")
    bot = FakeBot()
    _freeze_time(monkeypatch)

    with caplog.at_level("WARNING", logger="features.poke"):
        assert asyncio.run(handle_poke(bot, "111", "222", "333")) is None

    assert "replies" in caplog.text

