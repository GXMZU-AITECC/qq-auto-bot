"""官方 QQ 机器人平台（botpy）客户端。

对功能层暴露的调用契约：
  - on_message(bot, group_id, user_id, text) 回调，返回字符串则由本客户端发回
  - send_group_msg(group_id, text)
  - send_group_image(group_id, url)
  - get_group_member_name(group_id, user_id)

事件与回复：
  - 群聊：默认走 on_group_at_message_create（必须 @机器人）；群主在群设置开启「全部
    消息」后，所有群消息（含 @ 的）都改走 on_group_message_create（botpy 未实现，见
    下方补丁），此时 @ 前缀不被平台剥掉，需手动处理。
  - 私聊：on_c2c_message_create。
  - 都用 `message.reply()`（带 msg_id）发回复，即**被动回复**，不占主动消息额度
    （主动私聊每月仅 4 条，故必须走被动）。

注意：这里的 group_id / user_id 是官方平台的 openid（**不是群号 / QQ 号**），
且同一用户在不同群里 openid 不同；私聊无群，group_id 用对方 openid 顶替。
"""

import logging
import re

import botpy
from botpy.connection import ConnectionState
from botpy.message import C2CMessage, GroupMessage

logger = logging.getLogger("bot")

# 全量群消息模式下，@机器人 的消息平台不剥 @ 前缀，content 形如 "@机器人名 正文"
_AT_PREFIX = re.compile(r"^@\S+\s*")


def _patch_group_message_create() -> None:
    """给 botpy 补上 GROUP_MESSAGE_CREATE（群全量消息）的 parser。

    群主把「机器人可获取的群聊消息范围」设为「全部消息」后，非 @ 的群消息会以
    GROUP_MESSAGE_CREATE 下发；而 botpy 1.2.1 没实现它，只会打 `_parser unknown event`。
    平台按 ConnectionState 上 `parse_*` 方法名自动装配 parser，这里补一个同款即可。
    """
    if hasattr(ConnectionState, "parse_group_message_create"):
        return

    def parse_group_message_create(self, payload):
        message = GroupMessage(self.api, payload.get("id", None), payload.get("d", {}))
        self._dispatch("group_message_create", message)

    ConnectionState.parse_group_message_create = parse_group_message_create


_patch_group_message_create()


def _patch_group_author_username() -> None:
    """让 GroupMessage.author 带上 payload 里的 username。

    botpy 的 `GroupMessage._User` 只保留 `member_openid`，把 `username` 丢了；补上它，
    `get_group_member_name` 才能拿到昵称（官方平台没有成员信息接口，只能靠消息里带的）。
    """
    user_cls = GroupMessage._User
    if getattr(user_cls, "_username_patched", False):
        return

    def __init__(self, data):
        self.member_openid = data.get("member_openid", None)
        self.username = data.get("username", None)

    user_cls.__init__ = __init__
    user_cls._username_patched = True


_patch_group_author_username()


class BotPyClient(botpy.Client):
    def __init__(self, appid: str, secret: str, on_message, sandbox: bool = False):
        # 只订阅「群聊与单聊」事件（GROUP_AND_C2C_EVENT）。多带未授权的
        # intent（如 GUILD_MESSAGES）会被网关以 op=9 Invalid Session 断连。
        intents = botpy.Intents(public_messages=True)
        # bot_log=None + ext_handlers=False：botpy 不再自己写 botpy.log，其日志改为向 root
        # 传播，统一由 main._setup_logging() 的 handler 落到 logs/bot.log。
        super().__init__(
            intents=intents,
            is_sandbox=sandbox,
            bot_log=None,
            ext_handlers=False,
        )
        self._appid = appid
        self._secret = secret
        self.on_message = on_message
        # 官方平台没有成员信息查询接口，昵称只能从消息事件里攒（见 _handle_group）
        self._names: dict[str, str] = {}

    async def on_ready(self):
        logger.info(f"已连接官方平台，机器人：{self.robot.name}")

    async def on_group_at_message_create(self, message: GroupMessage):
        await self._handle_group(message)

    async def on_group_message_create(self, message: GroupMessage):
        # 群主开启「全部消息」后，群内所有消息（含非 @）都走这里
        await self._handle_group(message)

    async def _handle_group(self, message: GroupMessage):
        group_id = message.group_openid
        user_id = message.author.member_openid
        # 官方平台无成员信息接口，收到消息顺手把昵称攒下来，供 get_group_member_name 用
        name = getattr(message.author, "username", None)
        if name:
            self._names[user_id] = name
        # GROUP_AT_MESSAGE_CREATE 的 content 已去掉 @ 部分；GROUP_MESSAGE_CREATE（全量
        # 模式）不剥，需手动去掉行首 @ 前缀，否则 "@机器人名 /help" 匹配不到命令。
        text = _AT_PREFIX.sub("", (message.content or "").strip()).strip()
        logger.info(f"[群:{group_id}] {user_id}: {text}")

        if self.on_message:
            reply = await self.on_message(self, group_id, user_id, text)
            if reply:
                await message.reply(content=reply)

    async def on_c2c_message_create(self, message: C2CMessage):
        """私聊（单聊，无需 @）。无群，group_id 用会话方的 openid 顶替。"""
        user_id = message.author.user_openid
        text = (message.content or "").strip()
        logger.info(f"[私聊:{user_id}] {text}")

        if self.on_message:
            reply = await self.on_message(self, user_id, user_id, text)
            if reply:
                await message.reply(content=reply)

    async def send_group_msg(self, group_id: str, text: str):
        """群发纯文本（msg_type=0）"""
        await self.api.post_group_message(group_openid=group_id, msg_type=0, content=text)

    async def send_group_image(self, group_id: str, url: str):
        """群发图片（富媒体）。url 需是平台能下载到的公网地址。

        官方流程是「先上传换 file_info，再发 msg_type=7」，这里两步一起封掉。注意：
        富媒体消息不能同时带文本，要「图文」得发两条；本地文件不支持——botpy 1.2.1
        的上传接口只收 url，想发本地图片需自行做 base64 / 分片上传。
        """
        media = await self.api.post_group_file(
            group_openid=group_id, file_type=1, url=url
        )
        await self.api.post_group_message(
            group_openid=group_id, msg_type=7, media={"file_info": media["file_info"]}
        )

    async def get_group_member_name(self, group_id: str, user_id: str) -> str:
        """返回该成员昵称；没有成员信息接口，只能靠历史消息里攒的 username，兜底返回 user_id。"""
        return self._names.get(user_id) or str(user_id)

    async def stop(self):
        await self.close()

    async def start(self):  # noqa: D401 - 保持 main.py 的 await client.start() 形式
        await super().start(appid=self._appid, secret=self._secret)
