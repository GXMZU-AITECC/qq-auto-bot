from .scheduler import run

# 长驻后台任务（非消息驱动），由 main.py 在启动时拉起
STARTUP = [run]
