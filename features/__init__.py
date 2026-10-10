"""功能模块自动发现与命令路由。

规范：
- features/ 下每个子包就是一个功能模块
- 每个模块的 handler.py 必须导出 COMMANDS 字典（精确匹配）
- 可选导出 COMMAND_PATTERNS 字典（正则匹配，键为正则字符串）
- COMMANDS = {"/cmd": async_handler, ...}
- COMMAND_PATTERNS = {r"^关键词.+$": async_handler, ...}
- handler 签名: async def handler(bot, group_id, user_id, text) -> str | None
  text 是原始消息全文（用不到可以忽略），返回字符串则自动发送，返回 None 则静默
- 可选导出 STARTUP 列表（长驻后台协程，非消息驱动）: [async def fn(bot), ...]
  由 main.py 在启动时 create_task，退出时 cancel
"""

import importlib
import logging
import pkgutil
import re
from typing import Callable

logger = logging.getLogger("features")

_commands: dict[str, Callable] = {}
_patterns: list[tuple[re.Pattern, Callable]] = []
_startups: list[Callable] = []


def discover():
    """扫描 features/ 下所有模块，收集 COMMANDS 与 COMMAND_PATTERNS"""
    global _commands, _patterns, _startups
    _commands.clear()
    _patterns.clear()
    _startups.clear()

    for finder, name, ispkg in pkgutil.iter_modules(__path__):
        if not ispkg:
            continue
        try:
            mod = importlib.import_module(f"features.{name}.handler")
            for cmd, handler in getattr(mod, "COMMANDS", {}).items():
                if cmd in _commands:
                    logger.warning(f"命令 {cmd} 被多个功能注册，后面的覆盖前面的")
                _commands[cmd] = handler
                logger.info(f"注册命令 [{cmd}] ← features/{name}")
            for pat, handler in getattr(mod, "COMMAND_PATTERNS", {}).items():
                try:
                    compiled = re.compile(pat)
                except re.error as e:
                    logger.error(f"features/{name} 正则无效 {pat!r}: {e}")
                    continue
                _patterns.append((compiled, handler))
                logger.info(f"注册正则命令 [{pat}] ← features/{name}")
            for startup in getattr(mod, "STARTUP", []):
                _startups.append(startup)
                logger.info(f"注册启动任务 ← features/{name}")
        except Exception as e:
            logger.error(f"加载 features/{name} 失败: {e}")

    logger.info(f"共注册 {len(_commands)} 条命令、{len(_patterns)} 条正则命令")


async def _run(handler: Callable, bot, group_id: str, user_id: str, src: str) -> str | None:
    try:
        return await handler(bot, group_id, user_id, src)
    except Exception as e:
        logger.exception(f"执行命令 {src} 异常: {e}")
        return f"命令执行出错: {e}"


async def dispatch(bot, group_id: str, user_id: str, text: str) -> str | None:
    """路由消息：先精确匹配，再按注册顺序尝试正则全匹配"""
    handler = _commands.get(text)
    if handler is not None:
        return await _run(handler, bot, group_id, user_id, text)

    for compiled, handler in _patterns:
        if compiled.fullmatch(text):
            return await _run(handler, bot, group_id, user_id, text)

    return None  # 没有匹配的命令，静默


def startups() -> list[Callable]:
    """返回各功能注册的启动协程（签名 async def fn(bot) -> None，长驻运行）"""
    return list(_startups)
