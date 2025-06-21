import logging
import shutil
from asyncio import TaskGroup
from pathlib import Path, PurePath
from tempfile import TemporaryDirectory
from typing import cast

from asyncinotify import Event, Mask, RecursiveWatcher

from .drive import DriveUploader
from .lib import compress_to_path


_L = logging.getLogger(__name__)

_META_FILE_NAME = "galleryinfo.txt"


async def watch_finished_hah(
    *,
    hah_path: Path,
    uploader: DriveUploader,
    upload_to: PurePath,
    group: TaskGroup,
) -> None:
    download_path = hah_path / "download"

    watcher = RecursiveWatcher(download_path, Mask.CREATE)
    async for _event in watcher.watch_recursive():  # type: ignore
        event = cast(Event, _event)
        path = event.path
        if not path:
            continue
        if path.name == _META_FILE_NAME:
            gallery_path = path.parent
            group.create_task(_upload(uploader, gallery_path, upload_to))


def upload_finished_hah(
    *, hah_path: Path, uploader: DriveUploader, upload_to: PurePath, group: TaskGroup
):
    download_path = hah_path / "download"

    finished: list[Path] = []
    for candidate in download_path.iterdir():
        meta_path = candidate / _META_FILE_NAME
        if meta_path.is_file():
            group.create_task(_upload(uploader, candidate, upload_to))
            finished.append(candidate)
    return finished


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
