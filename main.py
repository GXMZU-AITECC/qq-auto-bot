import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from bot import OneBotClient
from config import get
from features import discover, dispatch, startups


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

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


logger = logging.getLogger("main")


async def on_message(bot: OneBotClient, group_id: str, user_id: str, text: str):
    reply = await dispatch(bot, group_id, user_id, text)
    if reply:
        await bot.send_group_msg(group_id, reply)


async def _start_web():
    """启动网页数据统计服务（config.yaml 中 web.enabled=true 时启用）"""
    from web.server import start

    await start(
        get("web", "host", default="127.0.0.1"),
        get("web", "port", default=8000),
    )


async def _run_startup(fn, bot):
    """运行功能注册的长驻协程；异常在此记录（功能内部不写日志）"""
    try:
        await fn(bot)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception(f"启动任务异常: {e}")


async def _cancel(*tasks):
    for t in tasks:
        if t:
            t.cancel()
    for t in tasks:
        if t:
            try:
                await t
            except asyncio.CancelledError:
                pass


async def main():
    discover()
    logger.info("启动 QQ 机器人...")
    client = OneBotClient(
        ws_url=get("llonebot", "ws_url", default="ws://127.0.0.1:3001"),
        http_url=get("llonebot", "http_url", default="http://127.0.0.1:3000"),
        on_message=on_message,
    )

    web_task = None
    if get("web", "enabled", default=False):
        logger.info(f"启动网页数据统计: http://{get('web', 'host', default='127.0.0.1')}:{get('web', 'port', default=8000)}")
        web_task = asyncio.create_task(_start_web())

    feature_tasks = [asyncio.create_task(_run_startup(fn, client)) for fn in startups()]

    try:
        await client.start()
    except KeyboardInterrupt:
        logger.info("收到退出信号")
    finally:
        await client.stop()
        await _cancel(web_task, *feature_tasks)
        logger.info("机器人已停止")


if __name__ == "__main__":
    _setup_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
