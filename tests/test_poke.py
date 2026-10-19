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
