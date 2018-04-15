import asyncio
import argparse
import signal

from aiohttp import web as aw
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

        self._loop = asyncio.get_event_loop()
        self._finished = asyncio.Event()

    def __call__(self):
        self._loop.create_task(self._amain())
        self._loop.add_signal_handler(signal.SIGINT, self._close_from_signal)
        self._loop.run_forever()
        self._loop.close()
        return 0

    async def _amain(self):
        application = aw.Application()

        application.router.add_view(r'/api/v1/torrents', api.TorrentsHandler)
        application.router.add_view(r'/api/v1/torrents/{torrent_id:\d+}', api.TorrentsHandler)

        async with drive.DriveUploader() as uploader, \
                   HaHContext(uploader), \
                   DiskSpaceContext(), \
                   ServerContext(application):
            application['uploader'] = uploader
            await self._wait_for_finished()

        self._loop.stop()

    def _close_from_signal(self):
        self._finished.set()

    async def _wait_for_finished(self):
        await self._finished.wait()


class HaHContext(object):

    def __init__(self, uploader):
        tmp = settings['hah']
        if not tmp:
            self._listener = None
        else:
            self._listener = hah.HaHListener(tmp['log_path'],
                                             tmp['download_path'],
                                             settings['upload_to'],
                                             uploader)

    async def __aenter__(self):
        if self._listener:
            self._listener.start()
        return self._listener

    async def __aexit__(self, exc_type, exc, tb):
        if self._listener:
            self._listener.stop()


class DiskSpaceContext(object):

    def __init__(self):
        if settings['reserved_space_in_gb']:
            self._listener = torrent.DiskSpaceListener()
        else:
            self._listener = None

    async def __aenter__(self):
        if self._listener:
            self._listener.start()
        return self._listener

    async def __aexit__(self, exc_type, exc, tb):
        if self._listener:
            self._listener.stop()


class ServerContext(object):

    def __init__(self, app):
        self._runner = aw.AppRunner(app)

    async def __aenter__(self):
        await self._runner.setup()
        site = aw.TCPSite(self._runner, port=settings['port'])
        await site.start()
        return self._runner

    async def __aexit__(self, exc_type, exc, tb):
        await self._runner.cleanup()


def parse_args(args):
    parser = argparse.ArgumentParser(prog='duld',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-s', '--settings', default='duld.yaml', type=str,
                        help='settings file name')
    args = parser.parse_args(args[1:])
    return args
