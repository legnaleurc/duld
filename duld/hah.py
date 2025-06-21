import logging
import re
import shutil
from asyncio import TaskGroup
from pathlib import Path, PurePath
from tempfile import TemporaryDirectory
from typing import cast

from asyncinotify import Event, Mask, RecursiveWatcher

from .drive import DriveUploader
from .lib import compress_to_path, is_too_long_to_compress


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
) -> list[Path]:
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
        _L.info(f"hah ignored deleted path: {src_path}")
        return

    with TemporaryDirectory() as tmp:
        work_path = Path(tmp)

        compress_base_name, remote_name = _get_names_for_upload(src_path, work_path)

        try:
            _L.info(f"compressing {src_path} to {work_path} ...")
            tmp_path = await compress_to_path(
                src_path, work_path, base_name=compress_base_name
            )

            _L.info(f"hah upload {tmp_path}")
            await uploader.upload_from_hah(dst_path, tmp_path, remote_name=remote_name)
        except Exception:
            _L.exception(f"trying to upload {src_path} to {dst_path} but failed")
            return

    # clean up
    _L.debug(f"rm -rf {src_path}")
    shutil.rmtree(src_path, ignore_errors=True)


def _get_names_for_upload(src_path: Path, dst_path: Path) -> tuple[str, str]:
    compress_base_name = src_path.name
    remote_name = f"{src_path.name}.7z"

    if _is_src_too_long(src_path.name):
        remote_name = _get_long_remote_name(src_path)
        return compress_base_name, remote_name

    if is_too_long_to_compress(dst_path, src_path.name):
        compress_base_name = _get_gid_from_name(src_path.name)
        return compress_base_name, remote_name

    return compress_base_name, remote_name


def _is_src_too_long(name: str) -> bool:
    # H@H will use gid as the directory name to workaround file name too long error.
    rv = re.match(r"^\d+$", name)
    return rv is not None


def _get_long_remote_name(src_path: Path) -> str:
    gid = src_path.name
    title = _read_title_from_meta(src_path)
    remote_name = f"{title} [{gid}].7z"
    return remote_name


def _read_title_from_meta(gallery_path: Path) -> str:
    meta_path = gallery_path / _META_FILE_NAME
    with meta_path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if line.startswith("Title:"):
                return line.split(":", 1)[1].strip()
    raise ValueError(f"no title found in {meta_path}")


def _get_gid_from_name(name: str) -> str:
    rv = re.match(r"[(\d+)]$", name)
    if rv is None:
        raise ValueError(f"unexpected name: {name}")
    gid = rv.group(1)
    return gid
