import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from bot_official import BotPyClient
from config import get
from features import discover, dispatch


def _setup_logging():
    level = get("log", "level", default="INFO")
    log_file = get("log", "file", default="logs/bot.log")
    max_bytes = get("log", "max_mb", default=10) * 1024 * 1024
    backup_count = get("log", "backup_count", default=5)

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # 先清掉已有 root handler——botpy 在 import 时 logging.basicConfig() 会加一个，
    # 不清的话控制台会重复打印
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


logger = logging.getLogger("main")


async def on_message(bot, group_id: str, user_id: str, text: str):
    """交给功能层处理，返回要发回的内容；实际发送由各客户端负责。"""
    return await dispatch(bot, group_id, user_id, text)


def _build_client():
    """构造官方 QQ 机器人平台（botpy）客户端。"""
    appid = get("qqbot", "app_id", default="") or os.environ.get("QQBOT_APP_ID", "")
    secret = get("qqbot", "secret", default="") or os.environ.get("QQBOT_APP_SECRET", "")
    if not (appid and secret):
        raise RuntimeError(
            "未配置官方平台凭据：请在 config.yaml 填 qqbot.app_id / qqbot.secret，"
            "或设环境变量 QQBOT_APP_ID / QQBOT_APP_SECRET"
        )

    logger.info("使用官方 QQ 机器人平台（botpy）")
    client = BotPyClient(
        appid=appid,
        secret=secret,
        sandbox=get("qqbot", "sandbox", default=True),
        on_message=on_message,
    )
    # botpy 在 Client 初始化时把自己的 logger 钉死在 INFO，构造后按我们的配置同步
    logging.getLogger("botpy").setLevel(get("log", "level", default="INFO"))
    return client


async def main():
    discover()
    logger.info("启动 QQ 机器人...")
    client = _build_client()

    try:
        await client.start()
    except KeyboardInterrupt:
        logger.info("收到退出信号")
    finally:
        stop = getattr(client, "stop", None)
        if stop:
            await stop()
        logger.info("机器人已停止")


if __name__ == "__main__":
    _setup_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
