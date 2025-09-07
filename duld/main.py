import logging
import signal
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from asyncio import Event, TaskGroup, get_running_loop
from collections.abc import Coroutine
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path, PurePath

from aiohttp.web import Application, AppRunner, TCPSite
from wcpan.logging import ConfigBuilder

from .api import HaHHandler, LinksHandler, TorrentsHandler
from .drive import create_uploader
from .hah import watch_finished_hah
from .keys import CONTEXT, SCHEDULER, TORRENT_REGISTRY, UPLOADER
from .settings import load_from_path
from .torrent import create_torrent_registry, watch_disk_space


type _Runnable[T] = Coroutine[None, None, T]


_L = logging.getLogger(__name__)


class Daemon:
    def __init__(self, args: list[str]) -> None:
        from logging.config import dictConfig

        kwargs = _parse_args(args)
        self._cfg = load_from_path(kwargs.settings)
        dictConfig(
            ConfigBuilder(path=self._cfg.log_path, rotate=True)
            .add("duld", level="D")
            .add("wcpan", level="I")
            .to_dict()
        )
        self._finished = None

    async def __call__(self) -> int:
        loop = get_running_loop()
        self._finished = Event()
        loop.add_signal_handler(signal.SIGINT, self._close_from_signal)
        loop.add_signal_handler(signal.SIGTERM, self._close_from_signal)
        return await self._guard()

    async def _guard(self) -> int:
        try:
            return await self._main()
        except Exception:
            _L.exception("main function error")
        return 1

    async def _main(self) -> int:
        app = Application()

        # Create torrent registry from configuration
        torrent_registry = create_torrent_registry(self._cfg.torrent_list)

        # Add torrent routes if we have any torrent clients
        if torrent_registry.get_all_clients():
            app.router.add_view(r"/api/v1/torrents", TorrentsHandler)
            app.router.add_view(
                r"/api/v1/torrents/{client}/{torrent_id}", TorrentsHandler
            )

        if self._cfg.hah_path:
            app.router.add_view(r"/api/v1/hah", HaHHandler)
        app.router.add_view(r"/api/v1/links", LinksHandler)

        async with AsyncExitStack() as stack:
            app[CONTEXT] = self._cfg
            app[TORRENT_REGISTRY] = torrent_registry

            group = await stack.enter_async_context(TaskGroup())
            app[SCHEDULER] = group

            uploader = await stack.enter_async_context(
                create_uploader(
                    drive_config_path=self._cfg.drive_config_path,
                    exclude_data=self._cfg.exclude,
                    dvd_data=self._cfg.dvd,
                )
            )
            app[UPLOADER] = uploader

            if self._cfg.hah_path:
                await stack.enter_async_context(
                    _background(
                        group,
                        watch_finished_hah(
                            hah_path=Path(self._cfg.hah_path),
                            uploader=uploader,
                            upload_to=PurePath(self._cfg.upload_to),
                            group=group,
                        ),
                    )
                )

            if torrent_registry.get_all_clients() and self._cfg.reserved_space_in_gb:
                await stack.enter_async_context(
                    _background(
                        group,
                        watch_disk_space(
                            torrent_registry=torrent_registry,
                            disk_space=self._cfg.reserved_space_in_gb,
                        ),
                    )
                )

            await stack.enter_async_context(
                _server_context(app, self._cfg.host, self._cfg.port)
            )

            _L.info("server started")
            await self._wait_for_finished()

        return 0

    def _close_from_signal(self) -> None:
        assert self._finished
        self._finished.set()

    async def _wait_for_finished(self) -> None:
        assert self._finished
        await self._finished.wait()


@asynccontextmanager
async def _server_context(app: Application, host: str, port: int):
    runner = AppRunner(app)
    await runner.setup()
    try:
        site = TCPSite(runner, host=host, port=port)
        await site.start()
        yield
    finally:
        await runner.cleanup()


@asynccontextmanager
async def _background[T](group: TaskGroup, c: _Runnable[T]):
    task = group.create_task(c)
    try:
        yield
    finally:
        task.cancel()


def _parse_args(args: list[str]):
    parser = ArgumentParser(prog="duld", formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("-s", "--settings", type=str, help="settings file name")
    kwargs = parser.parse_args(args[1:])
    return kwargs
