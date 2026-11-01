"""抽卡功能：单抽 / 十连 / 保底 单测（不连 QQ，用假配置）。"""

import asyncio

import features
import features.gacha.handler as gacha
from features.gacha.handler import cmd_draw


def _patch(monkeypatch, enabled=True) -> dict:
    """把 load_feature_config 换成返回测试配置"""
    cfg = {"enabled": enabled}
    monkeypatch.setattr(gacha, "load_feature_config", lambda name: cfg)
    return cfg


def _draw(text):
    """跑一次 cmd_draw，抽卡不用 bot，传 None 即可"""
    return asyncio.run(cmd_draw(None, "111", "222", text))


def test_导出了抽卡命令与正则():
    assert gacha.COMMANDS["/抽卡"] is cmd_draw
    assert r"^/抽卡\s+.*$" in gacha.COMMAND_PATTERNS


def test_discover_能收走抽卡命令与正则():
    features.discover()
    assert features._commands["/抽卡"] is cmd_draw
    assert any(pat.pattern == r"^/抽卡\s+.*$" for pat, _ in features._patterns)


def test_未启用时静默(monkeypatch):
    _patch(monkeypatch, enabled=False)
    for text in ("/抽卡", "/抽卡 十连", "/抽卡 其他"):
        assert _draw(text) is None


def test_单抽返回一条结果(monkeypatch):
    _patch(monkeypatch)
    out = _draw("/抽卡")
    assert out.startswith("🎴 抽卡结果：【")
    assert "\n" not in out


def test_十连恰好返回十张(monkeypatch):
    _patch(monkeypatch)
    lines = _draw("/抽卡 十连").split("\n")
    assert lines[0] == "🎴 十连结果："
    assert len(lines) == 11  # 标题 + 10 张


def test_十连逐条编号(monkeypatch):
    _patch(monkeypatch)
    lines = _draw("/抽卡 十连").split("\n")[1:]
    for i, line in enumerate(lines, start=1):
        assert line.startswith(f"{i}. 【")


def test_多轮十连都满足保底():
    for _ in range(500):
        cards = gacha.draw_ten()
        assert len(cards) == 10
        assert any(rarity in gacha.GUARANTEE_RARITIES for _, rarity, _ in cards)


def test_全白时保底替换最后一张并标记(monkeypatch):
    monkeypatch.setattr(gacha, "draw_card", lambda: ("烧掉的电源", "白"))
    cards = gacha.draw_ten()

    assert len(cards) == 10
    assert all(guaranteed is False for _, _, guaranteed in cards[:-1])
    name, rarity, guaranteed = cards[-1]
    assert guaranteed is True
    assert rarity in gacha.GUARANTEE_RARITIES
    assert name in gacha.CARD_POOL[rarity]


def test_已有蓝以上时不触发保底(monkeypatch):
    seq = iter([("激光雷达", "蓝")] + [("烧掉的电源", "白")] * 9)
    monkeypatch.setattr(gacha, "draw_card", lambda: next(seq))
    cards = gacha.draw_ten()

    assert all(guaranteed is False for _, _, guaranteed in cards)
    assert cards[0][1] == "蓝"


def test_未知参数给用法提示(monkeypatch):
    _patch(monkeypatch)
    for text in ("/抽卡 二十连", "/抽卡 单抽", "/抽卡 abc", "/抽卡 十连抽"):
        assert _draw(text) == gacha.USAGE


def test_参数前后多余空格也能识别(monkeypatch):
    _patch(monkeypatch)
    assert _draw("/抽卡   十连  ").startswith("🎴 十连结果：")
