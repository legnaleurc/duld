import datetime
import logging
import logging.handlers

from . import settings


class Logger(object):

    def __init__(self, name, level):
        super().__init__()
        self._logger = logging.getLogger(name)
        self._level = level
        self._parts = []

    def __lshift__(self, part):
        self._parts.append(part)
        return self

    def __del__(self):
        msg = ' '.join(self._parts)
        log = getattr(self._logger, self._level)
        log(msg)


def setup_logger():
    # log for daemon
    formatter = logging.Formatter('{asctime}|{levelname:_<8}|{message}',
                                  style='{')
    handler = create_handler(settings['log_path'], formatter)
    bind_to_logger(handler, (
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


def DEBUG(name):
    return Logger(name, 'debug')


def INFO(name):
    return Logger(name, 'info')


def WARNING(name):
    return Logger(name, 'warning')


def ERROR(name):
    return Logger(name, 'error')


def CRITICAL(name):
    return Logger(name, 'critical')


def EXCEPTION(name):
    return Logger(name, 'exception')
