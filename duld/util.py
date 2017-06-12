import argparse
import signal

from tornado import web as tw, ioloop as ti, httpserver as ths
from wcpan.listen import create_sockets
from wcpan.logger import setup as setup_logger

from . import api, drive, hah, settings, torrent


def main(args):
    args = parse_args(args)
    settings.reload(args.settings)
    setup_logger((
        'tornado.access',
        'tornado.application',
        'tornado.general',
        'wcpan.drive.google',
        'wcpan.worker',
        'duld',
    ), settings['log_path'])

    main_loop = ti.IOLoop.instance()

    uploader = drive.DriveUploader()
    uploader.initialize()

    hah_listener = None
    if settings['hah']:
        hah_listener = hah.HaHListener(settings['hah']['log_path'],
                                       settings['hah']['download_path'],
                                       settings['upload_to'],
                                       uploader)
    disk_space_listener = None
    if settings['reserved_space_in_gb']:
        disk_space_listener = torrent.DiskSpaceListener()

    application = tw.Application([
        (r'^/torrents$', api.TorrentsHandler),
        (r'^/torrents/(\d+)$', api.TorrentsHandler),
    ], uploader=uploader)
    server = ths.HTTPServer(application)

    async def real_close():
        if hah_listener:
            hah_listener.close()
        if disk_space_listener:
            disk_space_listener.close()
        async uploader.close()
        main_loop.stop()
    def close(signum, frame):
        main_loop.add_callback_from_signal(real_close)
    signal.signal(signal.SIGINT, close)

    with create_sockets([settings['port']]) as sockets:
        server.add_sockets(sockets)
        main_loop.start()
        main_loop.close()

    return 0


def parse_args(args):
    parser = argparse.ArgumentParser(prog='duld',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-s', '--settings', default='duld.yaml', type=str,
                        help='settings file name')
    args = parser.parse_args(args[1:])
    return args
