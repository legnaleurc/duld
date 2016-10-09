import os
import os.path as op
import pathlib
import re
import shutil

from tornado import ioloop as ti
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from wcpan.logger import DEBUG, ERROR

from . import settings


class HaHEventHandler(PatternMatchingEventHandler):

    def __init__(self, log_path, download_path, uploader):
        super(HaHEventHandler, self).__init__(patterns=[
            log_path,
        ])
        self._log_path = log_path
        self._download_path = pathlib.Path(download_path)
        self._uploader = uploader
        self._index = op.getsize(log_path)
        self._loop = ti.IOLoop.current()
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
        paths = self._download_path.glob('{0}*'.format(name))
        paths = list(paths)
        if len(paths) != 1:
            ERROR('tmacd') << '(hah)' << name << 'has multiple target'
            return
        self._loop.add_callback(self._upload, paths[1])

    async def _upload(self, path):
        DEBUG('tmacd') << 'hah upload' << path
        await self._uploader.upload_path(settings['upload_to'], str(path))
        DEBUG('tmacd') << 'rm -rf' << path
        shutil.rmtree(str(path), ignore_errors=True)


class HaHListener(object):

    def __init__(self, log_path, download_path, uploader):
        handler = HaHEventHandler(op.join(log_path, 'log_out'), download_path, uploader)
        self._observer = Observer()
        self._observer.schedule(handler, log_path)
        self._observer.start()

    def close(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
