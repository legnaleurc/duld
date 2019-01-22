import asyncio
import argparse
import contextlib as cl
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

        self._finished = asyncio.Event()

    def __call__(self):
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, self._close_from_signal)
        loop.add_signal_handler(signal.SIGTERM, self._close_from_signal)
        return await self._guard()

    async def _guard(self):
        try:
            return await self._main()
        except Exception as e:
            EXCEPTION('duld', e)
        return 1

    async def _main(self):
        app = aw.Application()

        app.router.add_view(r'/api/v1/torrents', api.TorrentsHandler)
        app.router.add_view(r'/api/v1/torrents/{torrent_id:\d+}', api.TorrentsHandler)

        async with cl.AsyncExitStack() as stack:
            uploader = await stack.enter_async_context(drive.DriveUploader())

            tmp = settings['hah']
            if tmp:
                await stack.enter_async_context(
                    hah.HaHListener(
                        tmp['log_path'],
                        tmp['download_path'],
                        settings['upload_to'],
                        uploader))

            if settings['reserved_space_in_gb']:
                stack.enter_context(torrent.DiskSpaceListener())

            app['uploader'] = uploader

            await stack.enter_async_context(ServerContext(app))

            await self._wait_for_finished()

        return 0

    def _close_from_signal(self):
        self._finished.set()

    async def _wait_for_finished(self):
        await self._finished.wait()


class ServerContext(object):

    def __init__(self, app):
        self._runner = aw.AppRunner(app)

    async def __aenter__(self):
        await self._runner.setup()
        site = aw.TCPSite(self._runner, host='127.0.0.1', port=settings['port'])
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
sys.exit(asyncio.run(main()))
