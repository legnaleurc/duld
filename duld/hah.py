import asyncio
import glob
import os
import os.path as op
import pathlib
import re
import shutil

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from wcpan.logger import DEBUG, ERROR


class HaHEventHandler(PatternMatchingEventHandler):

    def __init__(self, log_path, download_path, upload_path, uploader):
        super(HaHEventHandler, self).__init__(patterns=[
            log_path,
        ])
        self._log_path = log_path
        self._download_path = pathlib.Path(download_path)
        self._upload_path = upload_path
        self._uploader = uploader
        self._index = op.getsize(log_path)
        self._loop = asyncio.get_event_loop()
        self._lines = []

    def on_modified(self, event):
        if op.getsize(self._log_path) < self._index:
            self._index = 0
        with open(self._log_path, 'r') as fin:
            fin.seek(self._index, os.SEEK_SET)
            lines = fin.readlines()
            self._index = fin.tell()
        # the log may be truncated
        self._push_lines(lines)

    def _push_lines(self, lines):
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

            self._parse_line(line)
            self._lines.pop(0)

    def _parse_line(self, line):
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
        self._loop.create_task(self._upload(paths[0]))

    async def _upload(self, path):
        DEBUG('duld') << 'hah upload' << path
        await self._uploader.upload_path(self._upload_path, str(path))
        DEBUG('duld') << 'rm -rf' << path
        shutil.rmtree(str(path), ignore_errors=True)


class HaHListener(object):

    def __init__(self, log_path, download_path, upload_path, uploader):
        path = op.join(log_path, 'log_out')
        handler = HaHEventHandler(path, download_path, upload_path, uploader)
        self._observer = Observer()
        self._observer.schedule(handler, log_path)

    def __enter__(self):
        self._observer.start()
        return self

    def __exit__(self, type_, exc, tb):
        self._observer.stop()
        self._observer.join()
