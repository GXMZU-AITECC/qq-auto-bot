import asyncio
import json
import logging
import httpx
import websockets

logger = logging.getLogger("bot")


class OneBotClient:
    """连接 LLOneBot 的客户端，收消息 + 发 API 请求"""

    def __init__(self, ws_url: str, http_url: str, on_message):
        self.ws_url = ws_url
        self.http_url = http_url.rstrip("/")
        self.on_message = on_message
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._http = httpx.AsyncClient(timeout=10)
        self._running = False

    async def start(self):
        self._running = True
        while self._running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self._ws = ws
                    logger.info(f"已连接到 LLOneBot WebSocket: {self.ws_url}")
                    async for raw in ws:
                        try:
                            event = json.loads(raw)
                            await self._handle_event(event)
                        except json.JSONDecodeError:
                            logger.warning(f"收到非 JSON 数据: {raw[:100]}")
                        except Exception as e:
                            logger.exception(f"处理事件异常: {e}")
            except websockets.ConnectionClosed:
                logger.warning("连接断开，准备重连...")
            except OSError as e:
                logger.warning(f"连接失败 ({e})，准备重连...")
            if self._running:
                await asyncio.sleep(5)
        self._ws = None

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()
        await self._http.aclose()

    async def send_group_msg(self, group_id: str, text: str):
        """调用 LLOneBot HTTP API 发送群消息"""
        await self._api_call("send_group_msg", {"group_id": int(group_id), "message": text})

    async def send_private_msg(self, user_id: str, text: str):
        """调用 LLOneBot HTTP API 发送私聊消息"""
        await self._api_call("send_private_msg", {"user_id": int(user_id), "message": text})

    async def get_group_member_name(self, group_id: str, user_id: str) -> str:
        """获取群成员的昵称（优先返回群名片，其次昵称）"""
        result = await self._api_call("get_group_member_info", {
            "group_id": int(group_id),
            "user_id": int(user_id),
        })
        if result and result.get("data"):
            info = result["data"]
            return info.get("card") or info.get("nickname") or str(user_id)
        return str(user_id)

    async def _api_call(self, action: str, params: dict) -> dict | None:
        url = f"{self.http_url}/{action}"
        try:
            resp = await self._http.post(url, json=params)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "ok":
                logger.warning(f"API {action} 返回非 ok: {data}")
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"API {action} HTTP {e.response.status_code}: {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"API {action} 请求失败: {e}")
            return None

    async def _handle_event(self, event: dict):
        post_type = event.get("post_type")
        if post_type == "message":
            msg_type = event.get("message_type")
            if msg_type == "group":
                await self._handle_group_message(event)

    async def _handle_group_message(self, event: dict):
        group_id = str(event.get("group_id", ""))
        user_id = str(event.get("user_id", ""))
        raw_msg = event.get("raw_message", "")
        text = _extract_text(event.get("message", []))

        logger.info(f"[群:{group_id}] {user_id}: {raw_msg}")

        # 调用外部处理函数
        if self.on_message:
            await self.on_message(self, group_id, user_id, text.strip())


def _extract_text(msgs: list) -> str:
    """从 OneBot 数组格式消息中提取纯文本"""
    parts = []
    for seg in msgs:
        if isinstance(seg, dict) and seg.get("type") == "text":
            parts.append(seg.get("data", {}).get("text", ""))
    return "".join(parts)
