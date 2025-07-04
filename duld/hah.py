import glob
import logging
import os
import re
import shutil
from asyncio import TaskGroup
from pathlib import Path, PurePath
from tempfile import TemporaryDirectory

from asyncinotify import Inotify, Mask

from .drive import DriveUploader
from .lib import compress_to_path


_L = logging.getLogger(__name__)


class _LogParser(object):
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
        path_list = (path for path in path_list if path)
        unique_path_set = set(path_list)
        return list(unique_path_set)

    def flush(self) -> None:
        self._offset = self._log_path.stat().st_size
        self._buffer = []

    def _read_new_lines(self) -> None:
        if self._offset > self._log_path.stat().st_size:
            # log rotated, scan from the scratch
            self._offset = 0
        with self._log_path.open("r", errors="ignore") as fin:
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

    def _parse_line(self, line: str) -> Path | None:
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
            _L.error(f"(hah) {name} has multiple target {paths}")
            return
        return paths[0]


async def watch_hah_log(
    *,
    hah_path: Path,
    uploader: DriveUploader,
    upload_to: PurePath,
    group: TaskGroup,
):
    log_path = hah_path / "log"
    download_path = hah_path / "download"
    parse = _LogParser(log_path / "log_out", download_path)
    with Inotify() as watcher:
        watcher.add_watch(log_path, Mask.MODIFY)  # type: ignore
        try:
            async for _event in watcher:
                try:
                    path_list = parse()
                except Exception:
                    _L.exception("parser error")
                    parse.flush()
                    continue

                for path in path_list:
                    group.create_task(_upload(uploader, path, upload_to))
        except Exception:
            _L.exception("failed to pull from inotify")


def upload_finished(
    *, hah_path: Path, uploader: DriveUploader, upload_to: PurePath, group: TaskGroup
):
    lines = _get_existing_logs(hah_path)
    folders = (_parse_folder_name(_) for _ in lines)
    folder_table = {_[0]: _[1] for _ in folders if _}
    finished = (_parse_name(_) for _ in lines)
    finished = (folder_table.get(_, None) for _ in finished if _)
    finished_list = [_ for _ in finished if _]

    for real_name in finished_list:
        real_path = hah_path / "download" / real_name
        # TODO handle cancel
        group.create_task(_upload(uploader, real_path, upload_to))

    return finished_list


def _get_existing_logs(path: Path) -> list[str]:
    old_lines = _lines_from_path(path / "log" / "log_out.old")
    lines = _lines_from_path(path / "log" / "log_out")
    return old_lines + lines


def _lines_from_path(path: Path) -> list[str]:
    with open(path, "r") as fin:
        return list(fin.readlines())


def _parse_folder_name(line: str) -> tuple[str, str] | None:
    rv = re.search(r"Created directory download/(.*)", line)
    if not rv:
        return None
    real_name = rv.group(1)
    rv = re.match(r"^(.*) \[\d+\]$", real_name)
    if not rv:
        return None
    name = rv.group(1)
    return (name, real_name)


def _parse_name(line: str) -> str | None:
    rv = re.search(r"Finished download of gallery: (.*)", line)
    if not rv:
        return None
    return rv.group(1)


async def _upload(uploader: DriveUploader, src_path: Path, dst_path: PurePath) -> None:
    if not src_path.exists():
        _L.info(f"hah ignored deleted path {src_path}")
        return
    try:
        with TemporaryDirectory() as tmp:
            work_path = Path(tmp)
            _L.info(f"compressing {src_path} to {work_path} ...")
            tmp_path = await compress_to_path(src_path, work_path)
            _L.info(f"hah upload {tmp_path}")
            await uploader.upload_from_hah(dst_path, tmp_path)
    except Exception:
        _L.exception(f"trying to upload {src_path} to {dst_path} but failed")
        return
    _L.debug(f"rm -rf {src_path}")
    shutil.rmtree(src_path, ignore_errors=True)
