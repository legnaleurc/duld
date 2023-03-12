import asyncio
import glob
from logging import getLogger
import os
import re
import shutil
from contextlib import AsyncExitStack, ExitStack, contextmanager
from pathlib import Path
from typing import Coroutine

from asyncinotify import Inotify, Mask

from .drive import DriveUploader


class HaHContext(object):
    def __init__(self, hah_path: str, upload_to: str, uploader: DriveUploader):
        self._hah_path = Path(hah_path) if hah_path else None
        self._upload_to = Path(upload_to)
        self._uploader = uploader
        self._raii = None

    async def __aenter__(self):
        async with AsyncExitStack() as stack:
            if self._hah_path:
                stack.enter_context(
                    HaHListener(
                        self._hah_path / "log",
                        self._hah_path / "download",
                        self._upload_to,
                        self._uploader,
                    )
                )
            self._raii = stack.pop_all()
        return self

    async def __aexit__(self, type_, exc, tb):
        await self._raii.aclose()
        self._raii = None

    def scan_finished(self):
        lines = self._get_logs()
        folders = (parse_folder_name(_) for _ in lines)
        forders = {_[0]: _[1] for _ in folders if _}
        finished = (parse_name(_) for _ in lines)
        finished = (forders.get(_, None) for _ in finished if _)
        finished = [_ for _ in finished if _]

        f = self._upload_all(finished)
        asyncio.create_task(f)

        return finished

    def _get_logs(self):
        old_lines = lines_from_path(self._hah_path / "log" / "log_out.old")
        lines = lines_from_path(self._hah_path / "log" / "log_out")
        return old_lines + lines

    async def _upload_all(self, finished: list[str]):
        for real_name in finished:
            try:
                real_path = self._hah_path / "download" / real_name
                await upload(self._uploader, self._upload_to, real_path)
            except Exception:
                # just skip error tasks
                pass


class HaHEventHandler(object):
    def __init__(
        self,
        log_path: Path,
        download_path: Path,
        upload_path: Path,
        uploader: DriveUploader,
    ):
        self._log_path = log_path
        self._download_path = download_path
        self._upload_path = upload_path
        self._uploader = uploader
        self._index = log_path.stat().st_size
        self._lines = []

    async def on_modified(self, event):
        if self._log_path.stat().st_size < self._index:
            self._index = 0
        with open(self._log_path, "r") as fin:
            fin.seek(self._index, os.SEEK_SET)
            lines = fin.readlines()
            self._index = fin.tell()
        # the log may be truncated
        await self._push_lines(lines)

    async def _push_lines(self, lines):
        self._lines.extend(lines)
        while self._lines:
            line = self._lines[0]
            if not line.endswith("\n"):
                if len(self._lines) <= 1:
                    # not enough buffer
                    break
                else:
                    self._lines.pop(0)
                    line += self._lines[0]

            await self._parse_line(line)
            self._lines.pop(0)

    async def _parse_line(self, line):
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

        await upload(self._uploader, self._upload_path, paths[0])


class HaHListener(object):
    def __init__(
        self,
        log_path: Path,
        download_path: Path,
        upload_path: Path,
        uploader: DriveUploader,
    ):
        self._log_path = log_path
        path = log_path / "log_out"
        self._handler = HaHEventHandler(path, download_path, upload_path, uploader)
        self._watcher = None
        self._raii = None

    def __enter__(self):
        with ExitStack() as stack:
            self._watcher = stack.enter_context(Inotify())
            self._watcher.add_watch(self._log_path, Mask.MODIFY)
            stack.enter_context(non_blocking(self._listen()))
            self._raii = stack.pop_all()
        return self

    def __exit__(self, type_, exc, tb):
        self._raii.close()
        self._watcher = None
        self._raii = None

    async def _listen(self):
        try:
            async for event in self._watcher:
                await self._handler.on_modified(event)
        except Exception:
            getLogger(__name__).debug(f"inotify stopped")


@contextmanager
def non_blocking(coro: Coroutine):
    task = asyncio.create_task(coro)
    yield task
    task.cancel()


def lines_from_path(path: Path):
    with open(path, "r") as fin:
        return list(fin.readlines())


def parse_folder_name(line: str):
    rv = re.search(r"Created directory download/(.*)", line)
    if not rv:
        return None
    real_name = rv.group(1)
    rv = re.match(r"^(.*) \[\d+\]$", real_name)
    if not rv:
        return None
    name = rv.group(1)
    return (name, real_name)


def parse_name(line: str):
    rv = re.search(r"Finished download of gallery: (.*)", line)
    if not rv:
        return None
    return rv.group(1)


async def upload(uploader: DriveUploader, dst_path: Path, src_path: Path):
    if not src_path.exists():
        getLogger(__name__).debug(f"hah ignored deleted path {src_path}")
        return
    getLogger(__name__).debug(f"hah upload {src_path}")
    ok = await uploader.upload_path(dst_path, src_path)
    if not ok:
        return
    getLogger(__name__).debug(f"rm -rf {src_path}")
    shutil.rmtree(src_path, ignore_errors=True)
