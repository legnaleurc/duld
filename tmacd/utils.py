import argparse
import signal

from tornado import web as tw, ioloop as ti, httpserver as ths
from wcpan.listen import create_sockets
from wcpan.logger import setup as setup_logger

from . import api, acd, settings


def main(args):
    args = parse_args(args)
    settings.reload(args.settings)
    setup_logger(settings['log_path'], (
        'tornado.access',
        'tornado.application',
        'tornado.general',
        'requests.packages.urllib3.connectionpool',
        'wcpan.acd',
        'wcpan.worker',
        'tmacd',))

    main_loop = ti.IOLoop.instance()

    uploader = acd.ACDUploader()

    application = tw.Application([
        (r'^/torrents$', api.TorrentsHandler),
        (r'^/torrents/(\d+)$', api.TorrentsHandler),
    ], uploader=uploader)
    server = ths.HTTPServer(application)

    signal.signal(signal.SIGINT, uploader.close)

    with create_sockets([settings['port']]) as sockets:
        server.add_sockets(sockets)
        main_loop.start()
        uploader.close()
        main_loop.close()

    return 0


def parse_args(args):
    parser = argparse.ArgumentParser(prog='tmacd',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-s', '--settings', default='tmacd.yaml', type=str,
                        help='settings file name')
    args = parser.parse_args(args[1:])
    return args
