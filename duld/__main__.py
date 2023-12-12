import asyncio
from logging import getLogger
from logging.config import dictConfig
from pathlib import Path, PurePath
import signal
import sys
from collections.abc import Coroutine
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TypeAlias
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

from aiohttp.web import Application, AppRunner, TCPSite
from wcpan.logging import ConfigBuilder

from .api import HaHHandler, TorrentsHandler
from .drive import create_uploader
from .hah import watch_hah_log
from .settings import load_from_path
from .torrent import watch_disk_space


Runnable: TypeAlias = Coroutine[None, None, None]


class Daemon(object):
    def __init__(self, args: list[str]):
        kwargs = parse_args(args)
        self._cfg = load_from_path(kwargs.settings)
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
                create_uploader(
                    drive_config_path=self._cfg.drive_config_path,
                    exclude_pattern=self._cfg.exclude_pattern,
                    exclude_url=self._cfg.exclude_url,
                )
            )
            app["uploader"] = uploader

            if self._cfg.hah_path:
                await stack.enter_async_context(
                    background(
                        watch_hah_log(
                            hah_path=Path(self._cfg.hah_path),
                            uploader=uploader,
                            upload_to=PurePath(self._cfg.upload_to),
                        )
                    )
                )

            if self._cfg.transmission and self._cfg.reserved_space_in_gb:
                await stack.enter_async_context(
                    background(
                        watch_disk_space(
                            transmission=self._cfg.transmission,
                            disk_space=self._cfg.reserved_space_in_gb,
                        )
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


@asynccontextmanager
async def background(c: Runnable):
    async with asyncio.TaskGroup() as group:
        task = group.create_task(c)
        try:
            yield
        finally:
            task.cancel()


def parse_args(args: list[str]):
    parser = ArgumentParser(prog="duld", formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("-s", "--settings", type=str, help="settings file name")
    kwargs = parser.parse_args(args[1:])
    return kwargs


main = Daemon(sys.argv)
sys.exit(asyncio.run(main()))
