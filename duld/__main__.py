import asyncio
import argparse
import signal
import sys

from aiohttp import web as aw
from wcpan.logger import setup as setup_logger, EXCEPTION

from . import api, drive, hah, settings, torrent


class Daemon(object):

    def __init__(self, args):
        args = parse_args(args)
        settings.reload(args.settings)
        setup_logger((
            'aiohttp',
            'wcpan.drive.google',
            'wcpan.worker',
            'duld',
        ), settings['log_path'])

        self._loop = asyncio.get_event_loop()
        self._finished = asyncio.Event()

    def __call__(self):
        self._loop.create_task(self._guard())
        self._loop.add_signal_handler(signal.SIGINT, self._close_from_signal)
        self._loop.run_forever()
        self._loop.close()
        return 0

    async def _guard(self):
        try:
            return await self._main()
        except Exception as e:
            EXCEPTION('duld', e)
        finally:
            self._loop.stop()
        return 1

    async def _main(self):
        app = aw.Application()

        app.router.add_view(r'/api/v1/torrents', api.TorrentsHandler)
        app.router.add_view(r'/api/v1/torrents/{torrent_id:\d+}', api.TorrentsHandler)

        async with UploaderContext(), \
                   HaHContext(uploader), \
                   DiskSpaceContext(), \
                   ServerContext(app):
            await self._wait_for_finished()

        return 0

    def _close_from_signal(self):
        self._finished.set()

    async def _wait_for_finished(self):
        await self._finished.wait()


class UploaderContext(object):

    def __init__(self, app):
        self._app = app
        self._uploader = drive.DriveUploader()

    async def __aenter__(self):
        await self._uploader.__aenter__()
        self._app['uploader'] = self._uploader
        return self._uploader

    async def __aexit__(self, exc_type, exc, tb):
        await self._uploader.__aexit__(exc_type, exc, tb)


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


main = Daemon(sys.argv)
exit_code = main()
sys.exit(exit_code)
