import argparse

from tornado import web as tw, ioloop as ti, httpserver as ths
from wcpan.listen import create_sockets

from . import api, log, settings


def main(args):
    args = parse_args(args)
    settings.reload(args.settings)
    log.setup_logger()

    main_loop = ti.IOLoop.instance()
    application = tw.Application([
        (r'^/torrents$', api.TorrentsHandler),
        (r'^/torrents/(\d+)$', api.TorrentsHandler),
    ])
    server = ths.HTTPServer(application)
    with create_sockets([settings['port']]) as sockets:
        server.add_sockets(sockets)
        main_loop.start()
        main_loop.close()

    return 0


def parse_args(args):
    parser = argparse.ArgumentParser(prog='tmacd',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-s', '--settings', default='tmacd.yaml', type=str,
                        help='settings file name')
    args = parser.parse_args(args[1:])
    return args
