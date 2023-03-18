import asyncio
import glob
from logging import getLogger
import os
import re
import shutil
from collections.abc import Callable, Coroutine
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from asyncinotify import Inotify, Mask

from .drive import DriveUploader


class HaHContext(object):
    def __init__(self, hah_path: str, upload_to: str, uploader: DriveUploader):
        self._hah_path = Path(hah_path)
        self._upload_to = Path(upload_to)
        self._uploader = uploader
        self._raii = None

    async def __aenter__(self):
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(
                LogWatcher(
                    self._hah_path / "log",
                    self._hah_path / "download",
                    self._upload,
                )
            )
            self._raii = stack.pop_all()
        return self

    async def __aexit__(self, type_, exc, tb):
        assert self._raii
        await self._raii.aclose()
        self._raii = None

    def scan_finished(self) -> list[str]:
        lines = get_existing_logs(self._hah_path)
        folders = (parse_folder_name(_) for _ in lines)
        folder_table = {_[0]: _[1] for _ in folders if _}
        finished = (parse_name(_) for _ in lines)
        finished = (folder_table.get(_, None) for _ in finished if _)
        finished_list = [_ for _ in finished if _]

        for real_name in finished_list:
            real_path = self._hah_path / "download" / real_name
            # TODO handle cancel
            asyncio.create_task(self._upload(real_path))

        return finished_list

    async def _upload(self, src_path: Path) -> None:
        if not src_path.exists():
            getLogger(__name__).info(f"hah ignored deleted path {src_path}")
            return
        getLogger(__name__).info(f"hah upload {src_path}")
        try:
            await self._uploader.upload_path(self._upload_to, src_path)
        except Exception:
            getLogger(__name__).exception(
                f"trying to upload {src_path} to {self._upload_to} but failed"
            )
            return
        getLogger(__name__).debug(f"rm -rf {src_path}")
        shutil.rmtree(src_path, ignore_errors=True)


class LogWatcher(object):
    def __init__(
        self,
        log_path: Path,
        download_path: Path,
        upload: Callable[[Path], Coroutine[None, None, None]],
    ):
        self._log_path = log_path
        path = log_path / "log_out"
        self._parse = LogParser(path, download_path)
        self._upload = upload
        self._watcher = None
        self._raii = None

    async def __aenter__(self):
        async with AsyncExitStack() as stack:
            self._watcher = stack.enter_context(Inotify())
            self._watcher.add_watch(self._log_path, Mask.MODIFY)
            await stack.enter_async_context(non_blocking(self._listen()))
            self._raii = stack.pop_all()
        return self

    async def __aexit__(self, type_, exc, tb):
        assert self._raii
        await self._raii.aclose()
        self._watcher = None
        self._raii = None

    async def _listen(self):
        assert self._watcher
        try:
            async for _event in self._watcher:
                path_list = self._parse()
                for path in path_list:
                    # TODO handle cancel
                    asyncio.create_task(self._upload(path))
        except Exception:
            getLogger(__name__).exception(f"failed to pull from inotify")


class LogParser(object):
    def __init__(
        self,
        log_path: Path,
        download_path: Path,
    ) -> None:
        self._log_path = log_path
        self._download_path = download_path
        self._offset = log_path.stat().st_size
        self._buffer: list[str] = []

    def __call__(self) -> list[Path]:
        self._read_new_lines()
        path_list = (self._parse_line(_) for _ in self._next_line())
        return [path for path in path_list if path]

    def _read_new_lines(self) -> None:
        if self._offset > self._log_path.stat().st_size:
            # log rotated, scan from the scratch
            self._offset = 0
        with open(self._log_path, "r") as fin:
            fin.seek(self._offset, os.SEEK_SET)
            lines = fin.readlines()
            self._offset = fin.tell()
        # the log may be truncated, push to the buffer first
        self._buffer.extend(lines)

    def _next_line(self):
        while self._buffer:
            line = self._buffer[0]
            if not line.endswith("\n"):
                if len(self._buffer) <= 1:
                    # not enough buffer
                    break
                else:
                    self._buffer.pop(0)
                    line += self._buffer[0]
            self._buffer.pop(0)
            yield line

    def _parse_line(self, line) -> Path | None:
        m = re.match(
            r".*\[info\] GalleryDownloader: Finished download of gallery: (.+)\n", line
        )
        if not m:
            return
        name = m.group(1)
        m = glob.escape(name)
        # H@H will strip long gallery name
        if len(m) > 99:
            m = m[:99]
        m = "{0}*".format(m)
        paths = self._download_path.glob(m)
        paths = list(paths)
        if len(paths) != 1:
            getLogger(__name__).error(f"(hah) {name} has multiple target {paths}")
            return
        return paths[0]


@asynccontextmanager
async def non_blocking(coro: Coroutine[None, None, None]):
    task = asyncio.create_task(coro)
    try:
        yield task
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            getLogger(__name__).debug("stopped hah log watcher")


def get_existing_logs(path: Path) -> list[str]:
    old_lines = lines_from_path(path / "log" / "log_out.old")
    lines = lines_from_path(path / "log" / "log_out")
    return old_lines + lines


def lines_from_path(path: Path) -> list[str]:
    with open(path, "r") as fin:
        return list(fin.readlines())


def parse_folder_name(line: str) -> tuple[str, str] | None:
    rv = re.search(r"Created directory download/(.*)", line)
    if not rv:
        return None
    real_name = rv.group(1)
    rv = re.match(r"^(.*) \[\d+\]$", real_name)
    if not rv:
        return None
    name = rv.group(1)
    return (name, real_name)


def parse_name(line: str) -> str | None:
    rv = re.search(r"Finished download of gallery: (.*)", line)
    if not rv:
        return None
    return rv.group(1)
