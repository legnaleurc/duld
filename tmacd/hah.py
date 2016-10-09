import os
import os.path as op
import re

from tornado import ioloop as ti
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from wcpan.logger import DEBUG

from . import settings


class HaHEventHandler(PatternMatchingEventHandler):

    def __init__(self, log_path, download_path, uploader):
        super(HaHEventHandler, self).__init__(patterns=[
            log_path,
        ])
        self._log_path = log_path
        self._download_path = download_path
        self._uploader = uploader
        self._index = op.getsize(log_path)
        self._loop = ti.IOLoop.current()
        self._lines = []
        self._current_gid = ''
        self._parse_line = self._parse_gid

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

    def _parse_gid(self, line):
        DEBUG('tmacd') << 'parse_gid' << line
        m = re.match(r'.*\[debug\] GalleryDownloader: Parsed gid=(\d+)\n', line)
        if m:
            self._current_gid = m.group(1)
            self._parse_line = self._parse_pre_title
        self._lines.pop(0)

    def _parse_pre_title(self, line):
        DEBUG('tmacd') << 'parse_gid' << line
        m = re.match(r'.*\[debug\] GalleryDownloader: Parsed title=(.+)\n', line)
        if m:
            self._parse_line = self._parse_post_title
        self._lines.pop(0)

    def _parse_post_title(self, line):
        DEBUG('tmacd') << 'parse_gid' << line
        m = re.match(r'.*\[info\] GalleryDownloader: Finished download of gallery: (.+)\n', line)
        if m:
            name = m.group(1)
            self._loop.add_callback(self._upload, '{0} [{1}]'.format(name, self._current_gid))
            self._current_gid = ''
        self._lines.pop(0)

    async def _upload(self, name):
        DEBUG('tmacd') << 'hah upload' << self._download_path << name
        # await self._uploader.upload_torrent(settings['upload_to'], self._download_path, [name])
        DEBUG('tmacd') << 'rm -rf' << op.join(self._download_path, name)


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
