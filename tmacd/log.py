import datetime
import logging
import logging.handlers

from wcpan.logger import setup

from . import settings


def setup_logger():
    # log for daemon
    setup(settings['log_path'], (
        'asyncio',
        'aiohttp.access',
        'aiohttp.client',
        'aiohttp.internal',
        'aiohttp.server',
        'aiohttp.web',
        'aiohttp.websocket',
        'tmacd',))

    # log for acdcli
    formatter = logging.Formatter('%(message)s')
    handler = create_handler(settings['acdcli_log_path'], formatter)
    bind_to_logger(handler, ('acd',))


def create_logger(name):
    logger = logging.getLogger(name)
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger


def create_handler(path, formatter):
    # alias
    TRFHandler = logging.handlers.TimedRotatingFileHandler
    # rotate on Sunday
    handler = TRFHandler(path, when='w6', atTime=datetime.time())
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    return handler


def bind_to_logger(handler, names):
    for name in names:
        logger = create_logger(name)
        logger.addHandler(handler)
