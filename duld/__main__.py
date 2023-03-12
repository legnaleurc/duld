import asyncio
import argparse
from logging import getLogger
from logging.config import dictConfig
import signal
import sys
from contextlib import AsyncExitStack

from aiohttp.web import Application, AppRunner, TCPSite
from wcpan.logging import ConfigBuilder

from . import api, drive, hah, settings, torrent


class Daemon(object):
    def __init__(self, args):
        args = parse_args(args)
        settings.reload(args.settings)
        dictConfig(
            ConfigBuilder(path=settings["log_path"], rotate=True)
            .add("wcpan", "duld", level="D")
            .to_dict()
        )

        self._finished = None

    async def __call__(self):
        loop = asyncio.get_running_loop()
        self._finished = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, self._close_from_signal)
        loop.add_signal_handler(signal.SIGTERM, self._close_from_signal)
        return await self._guard()

    async def _guard(self):
        try:
            return await self._main()
        except Exception:
            getLogger(__name__).exception("main function error")
        return 1

    async def _main(self):
        app = Application()

        app.router.add_view(r"/api/v1/torrents", api.TorrentsHandler)
        app.router.add_view(r"/api/v1/torrents/{torrent_id:\d+}", api.TorrentsHandler)
        app.router.add_view(r"/api/v1/hah", api.HaHHandler)

        async with AsyncExitStack() as stack:
            uploader = await stack.enter_async_context(drive.DriveUploader())

            hah_context = await stack.enter_async_context(
                hah.HaHContext(
                    settings["hah_path"],
                    settings["upload_to"],
                    uploader,
                )
            )

            if settings["reserved_space_in_gb"]:
                stack.enter_context(torrent.DiskSpaceListener())

            app["uploader"] = uploader
            app["hah"] = hah_context

            await stack.enter_async_context(ServerContext(app))

            await self._wait_for_finished()

        return 0

    def _close_from_signal(self):
        self._finished.set()

    async def _wait_for_finished(self):
        await self._finished.wait()


class ServerContext(object):
    def __init__(self, app):
        self._runner = AppRunner(app)

    async def __aenter__(self):
        await self._runner.setup()
        site = TCPSite(self._runner, host="127.0.0.1", port=settings["port"])
        await site.start()
        return self._runner

    async def __aexit__(self, exc_type, exc, tb):
        await self._runner.cleanup()


def parse_args(args):
    parser = argparse.ArgumentParser(
        prog="duld", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-s", "--settings", default="duld.yaml", type=str, help="settings file name"
    )
    args = parser.parse_args(args[1:])
    return args


main = Daemon(sys.argv)
sys.exit(asyncio.run(main()))
