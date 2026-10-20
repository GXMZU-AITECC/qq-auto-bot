"""bot.py 的事件分流：notice（戳一戳）过滤逻辑单测。

不连 QQ、不发网络请求：只把假事件喂给 _handle_event，看 on_poke / on_message
有没有被调用。重点覆盖「什么该处理、什么该丢掉」。
"""

import asyncio

from bot import OneBotClient

SELF_ID = 100000


async def _noop(*args, **kwargs):
    return None


def _make_client(on_poke, on_message=None) -> OneBotClient:
    return OneBotClient(
        "ws://127.0.0.1:0",
        "http://127.0.0.1:0",
        on_message=on_message or _noop,
        on_poke=on_poke,
    )


def _feed(client: OneBotClient, event: dict) -> None:
    """把一条事件喂进去，跑完顺手关掉 httpx 客户端（避免资源警告）"""

    async def run():
        try:
            await client._handle_event(event)
        finally:
            await client._http.aclose()

    asyncio.run(run())


def _poke_event(**over) -> dict:
    """一条「别人戳机器人」的标准事件，可用关键字改字段"""
    event = {
        "post_type": "notice",
        "notice_type": "notify",
        "sub_type": "poke",
        "self_id": SELF_ID,
        "group_id": 888,
        "user_id": 222,
        "target_id": SELF_ID,
    }
    event.update(over)
    return event


def _recorder():
    calls = []

    async def on_poke(bot, group_id, user_id, target_id):
        calls.append((group_id, user_id, target_id))

    return calls, on_poke


def test_别人戳机器人会转交():
    calls, on_poke = _recorder()
    _feed(_make_client(on_poke), _poke_event())
    assert calls == [("888", "222", str(SELF_ID))]


def test_机器人自己戳别人不触发():
    """反戳时自己发出的 poke 通知必须挡掉，否则会自己触发自己"""
    calls, on_poke = _recorder()
    _feed(_make_client(on_poke), _poke_event(user_id=SELF_ID, target_id=333333))
    assert calls == []


def test_群友互戳不触发():
    calls, on_poke = _recorder()
    _feed(_make_client(on_poke), _poke_event(user_id=222, target_id=333333))
    assert calls == []


def test_非戳一戳的通知不触发():
    calls, on_poke = _recorder()
    client = _make_client(on_poke)
    _feed(client, _poke_event(notice_type="group_increase", sub_type="approve"))
    _feed(client, _poke_event(sub_type="recall"))
    assert calls == []


def test_字符串与数字形式的_id都能匹配():
    """LLOneBot 有时给数字、有时给字符串，两种都得认"""
    calls, on_poke = _recorder()
    _feed(_make_client(on_poke), _poke_event(self_id=str(SELF_ID), target_id=SELF_ID))
    assert calls == [("888", "222", str(SELF_ID))]


def test_没有传on_poke时不报错():
    """老调用方式（只传 on_message）必须继续能跑"""
    _feed(_make_client(None), _poke_event())  # 不抛异常即通过


def test_群消息仍然走on_message():
    calls = []

    async def on_message(bot, group_id, user_id, text):
        calls.append((group_id, user_id, text))

    event = {
        "post_type": "message",
        "message_type": "group",
        "group_id": 888,
        "user_id": 222,
        "raw_message": "/抽卡",
        "message": [{"type": "text", "data": {"text": "/抽卡"}}],
    }
    _feed(_make_client(None, on_message), event)
    assert calls == [("888", "222", "/抽卡")]
