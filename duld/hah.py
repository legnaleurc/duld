import asyncio
import contextlib as cl
import glob
import os
import os.path as op
import pathlib
import re
import shutil

import aionotify
from wcpan.logger import DEBUG, ERROR


class HaHContext(object):

    def __init__(self, hah_path, upload_to, uploader):
        self._hah_path = pathlib.Path(hah_path) if hah_path else None
        self._upload_to = pathlib.Path(upload_to)
        self._uploader = uploader
        self._raii = None

    async def __aenter__(self):
        async with cl.AsyncExitStack() as stack:
            if self._hah_path:
                await stack.enter_async_context(
                    HaHListener(
                        self._hah_path / 'log',
                        self._hah_path / 'download',
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
        forders = { _[0]: _[1] for _ in folders if _ }
        finished = (parse_name(_) for _ in lines)
        finished = (forders.get(_, None) for _ in finished if _)
        finished = [_ for _ in finished if _]

        f = self._upload_all(finished)
        asyncio.create_task(f)

        return finished

    def _get_logs(self):
        old_lines = lines_from_path(self._hah_path / 'log' / 'log_out.old')
        lines = lines_from_path(self._hah_path / 'log' / 'log_out')
        return old_lines + lines

    async def _upload_all(self, finished):
        for real_name in finished:
            try:
                await self._upload(self._hah_path / 'download' / real_name)
            except Exception:
                # just skip error tasks
                pass

    async def _upload(self, path):
        DEBUG('duld') << 'hah upload' << path
        ok = await self._uploader.upload_path(self._upload_to, str(path))
        if not ok:
            return
        DEBUG('duld') << 'rm -rf' << path
        shutil.rmtree(str(path), ignore_errors=True)


class HaHEventHandler(object):

    def __init__(self, log_path, download_path, upload_path, uploader):
        super(HaHEventHandler, self).__init__()
        self._log_path = log_path
        self._download_path = pathlib.Path(download_path)
        self._upload_path = upload_path
        self._uploader = uploader
        self._index = op.getsize(log_path)
        self._lines = []

    async def on_modified(self, event):
        if op.getsize(self._log_path) < self._index:
            self._index = 0
        with open(self._log_path, 'r') as fin:
            fin.seek(self._index, os.SEEK_SET)
            lines = fin.readlines()
            self._index = fin.tell()
        # the log may be truncated
        await self._push_lines(lines)

    async def _push_lines(self, lines):
        self._lines.extend(lines)
        while self._lines:
            line = self._lines[0]
            if not line.endswith('\n'):
                if len(self._lines) <= 1:
                    # not enough buffer
                    break
                else:
                    self._lines.pop(0)
                    line += self._lines[0]

            await self._parse_line(line)
            self._lines.pop(0)

    async def _parse_line(self, line):
        m = re.match(r'.*\[info\] GalleryDownloader: Finished download of gallery: (.+)\n', line)
        if not m:
            return
        name = m.group(1)
        m = glob.escape(name)
        # H@H will strip long gallery name
        if len(m) > 99:
            m = m[:99]
        m = '{0}*'.format(m)
        paths = self._download_path.glob(m)
        paths = list(paths)
        if len(paths) != 1:
            ERROR('duld') << '(hah)' << name << 'has multiple target' << paths
            return
        await self._upload(paths[0])

    async def _upload(self, path):
        DEBUG('duld') << 'hah upload' << path
        ok = await self._uploader.upload_path(self._upload_path, str(path))
        if not ok:
            return
        DEBUG('duld') << 'rm -rf' << path
        shutil.rmtree(str(path), ignore_errors=True)


class HaHListener(object):

    def __init__(self, log_path, download_path, upload_path, uploader):
        path = op.join(log_path, 'log_out')
        self._handler = HaHEventHandler(path, download_path, upload_path, uploader)
        self._watcher = aionotify.Watcher()
        self._watcher.watch(alias='logs', path=str(log_path), flags=aionotify.Flags.MODIFY)

    async def __aenter__(self):
        loop = asyncio.get_running_loop()
        await self._watcher.setup(loop)
        self._task = asyncio.create_task(self._listen())
        return self

    async def __aexit__(self, type_, exc, tb):
        self._task.cancel()
        self._watcher.close()

    async def _listen(self):
        while True:
            event = await self._watcher.get_event()
            await self._handler.on_modified(event)


def lines_from_path(path):
    with open(path, 'r') as fin:
        return list(fin.readlines())


def parse_folder_name(line):
    rv = re.search(r'Created directory download/(.*)', line)
    if not rv:
        return None
    real_name = rv.group(1)
    rv = re.match(r'^(.*) \[\d+\]$', real_name)
    if not rv:
        return None
    name = rv.group(1)
    return (name, real_name)


def parse_name(line):
    rv = re.search(r'Finished download of gallery: (.*)', line)
    if not rv:
        return None
    return rv.group(1)
