import argparse
import asyncio
import sys

from aiohttp import web

from . import handlers
from . import log
from . import settings


def main(args=None):
    if not args:
        args = sys.argv

    args = parse_args(args)
    settings.reload(args.settings)
    log.setup_logger()

    application = web.Application()
    # TODO cleanup pending tasks

    torrents = application.router.add_resource('/torrents/{id}')
    torrents.add_route('PUT', handlers.TorrentsHandler)

    web.run_app(application, host='127.0.0.1', port=settings['port'])

    return 0


def parse_args(args):
    parser = argparse.ArgumentParser(prog='tmacd',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-s', '--settings', default='tmacd.yaml', type=str,
                        help='settings file name')
    args = parser.parse_args(args[1:])
    return args
