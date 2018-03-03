import argparse
import signal

from tornado import web as tw, ioloop as ti, httpserver as ths
from wcpan.listen import create_sockets
from wcpan.logger import setup as setup_logger

from . import api, drive, hah, settings, torrent


class Shell(object):

    def __init__(self, args):
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

        self._loop = ti.IOLoop.instance()
        self._hah_listener = None
        self._disk_space_listener = None
        self._uploader = drive.DriveUploader()

    def __call__(self):
        self._loop.add_callback(self._amain)
        signal.signal(signal.SIGINT, self._close_from_signal)

        application = tw.Application([
            (r'^/torrents$', api.TorrentsHandler),
            (r'^/torrents/(\d+)$', api.TorrentsHandler),
        ], uploader=self._uploader)
        server = ths.HTTPServer(application)

        with create_sockets([settings['port']]) as sockets:
            server.add_sockets(sockets)
            main_loop.start()
            main_loop.close()

        return 0

    async def _amain(self):
        await self._uploader.initialize()

        if settings['hah']:
            tmp = settings['hah']
            self._hah_listener = hah.HaHListener(tmp['log_path'],
                                                 tmp['download_path'],
                                                 settings['upload_to'],
                                                 self._uploader)

        if settings['reserved_space_in_gb']:
            self._disk_space_listener = torrent.DiskSpaceListener()

    def _close_from_signal(self):
        self._loop.add_callback_from_signal(self._aclose)

    async def _aclose(self):
        if self._hah_listener:
            self._hah_listener.close()
        if self._disk_space_listener:
            self._disk_space_listener.close()
        await self._uploader.close()
        self._loop.stop()


def parse_args(args):
    parser = argparse.ArgumentParser(prog='duld',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-s', '--settings', default='duld.yaml', type=str,
                        help='settings file name')
    args = parser.parse_args(args[1:])
    return args
