import asyncio
import argparse
from logging import getLogger
from logging.config import dictConfig
import signal
import sys
from contextlib import AsyncExitStack, asynccontextmanager

from aiohttp.web import Application, AppRunner, TCPSite
from wcpan.logging import ConfigBuilder

from .api import HaHHandler, TorrentsHandler
from .drive import DriveUploader
from .hah import HaHContext
from .settings import load_from_path
from .torrent import disk_space_watcher


class Daemon(object):
    def __init__(self, args):
        args = parse_args(args)
        self._cfg = load_from_path(args.settings)
        dictConfig(
            ConfigBuilder(path=self._cfg.log_path, rotate=True)
            .add("duld", "__main__", level="D")
            .add("wcpan", level="I")
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

        if self._cfg.transmission:
            app.router.add_view(r"/api/v1/torrents", TorrentsHandler)
            app.router.add_view(r"/api/v1/torrents/{torrent_id:\d+}", TorrentsHandler)
        if self._cfg.hah_path:
            app.router.add_view(r"/api/v1/hah", HaHHandler)

        async with AsyncExitStack() as stack:
            app["ctx"] = self._cfg

            uploader = await stack.enter_async_context(
                DriveUploader(
                    exclude_pattern=self._cfg.exclude_pattern,
                    exclude_url=self._cfg.exclude_url,
                )
            )
            app["uploader"] = uploader

            if self._cfg.hah_path:
                hah_context = await stack.enter_async_context(
                    HaHContext(
                        self._cfg.hah_path,
                        self._cfg.upload_to,
                        uploader,
                    )
                )
                app["hah"] = hah_context

            if self._cfg.transmission and self._cfg.reserved_space_in_gb:
                await stack.enter_async_context(
                    disk_space_watcher(
                        self._cfg.transmission, self._cfg.reserved_space_in_gb
                    )
                )

            await stack.enter_async_context(server_context(app, self._cfg.port))

            getLogger(__name__).info("server started")
            await self._wait_for_finished()

        return 0

    def _close_from_signal(self):
        assert self._finished
        self._finished.set()

    async def _wait_for_finished(self):
        assert self._finished
        await self._finished.wait()


@asynccontextmanager
async def server_context(app: Application, port: int):
    runner = AppRunner(app)
    await runner.setup()
    try:
        site = TCPSite(runner, host="127.1", port=port)
        await site.start()
        site = TCPSite(runner, host="::1", port=port)
        await site.start()
        yield
    finally:
        await runner.cleanup()


def parse_args(args):
    parser = argparse.ArgumentParser(
        prog="duld", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("-s", "--settings", type=str, help="settings file name")
    args = parser.parse_args(args[1:])
    return args


main = Daemon(sys.argv)
sys.exit(asyncio.run(main()))
