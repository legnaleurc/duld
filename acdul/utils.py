import argparse
import signal

from tornado import web as tw, ioloop as ti, httpserver as ths
from wcpan.listen import create_sockets
from wcpan.logger import setup as setup_logger

from . import api, acd, hah, settings


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
        'acdul',))

    main_loop = ti.IOLoop.instance()

    uploader = acd.ACDUploader()

    hah_listener = None
    if settings['hah']:
        hah_listener = hah.HaHListener(settings['hah']['log_path'],
                                       settings['hah']['download_path'],
                                       settings['upload_to'],
                                       uploader)

    application = tw.Application([
        (r'^/torrents$', api.TorrentsHandler),
        (r'^/torrents/(\d+)$', api.TorrentsHandler),
    ], uploader=uploader)
    server = ths.HTTPServer(application)

    def close(signum, frame):
        if hah_listener:
            hah_listener.close()
        uploader.close()
        main_loop.stop()
    signal.signal(signal.SIGINT, close)

    with create_sockets([settings['port']]) as sockets:
        server.add_sockets(sockets)
        main_loop.start()
        main_loop.close()

    return 0


def parse_args(args):
    parser = argparse.ArgumentParser(prog='acdul',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-s', '--settings', default='acdul.yaml', type=str,
                        help='settings file name')
    args = parser.parse_args(args[1:])
    return args
