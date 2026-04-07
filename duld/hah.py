import logging
import re
import shutil
from asyncio import TaskGroup
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from asyncinotify import Event, Mask, RecursiveWatcher

from .lib import compress_to_path, is_too_long_to_compress
from .upload import Uploader


_L = logging.getLogger(__name__)

_META_FILE_NAME = "galleryinfo.txt"
_LINUX_NAME_MAX = 255


async def watch_finished_hah(
    *,
    hah_path: Path,
    uploader: Uploader,
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
            group.create_task(_upload(uploader, gallery_path))


def upload_finished_hah(
    *, hah_path: Path, uploader: Uploader, group: TaskGroup
) -> list[Path]:
    download_path = hah_path / "download"

    finished: list[Path] = []
    for candidate in download_path.iterdir():
        meta_path = candidate / _META_FILE_NAME
        if meta_path.is_file():
            group.create_task(_upload(uploader, candidate))
            finished.append(candidate)
    return finished


async def _upload(uploader: Uploader, src_path: Path) -> None:
    if not src_path.exists():
        _L.info(f"hah ignored deleted path: {src_path}")
        return

    with TemporaryDirectory() as tmp:
        work_path = Path(tmp)

        try:
            compress_base_name, remote_name = _get_names_for_upload(src_path, work_path)

            _L.info(f"compressing {src_path} to {work_path} ...")
            tmp_path = await compress_to_path(
                src_path, work_path, base_name=compress_base_name
            )

            _L.info(f"hah upload {tmp_path}")
            await uploader.upload_from_hah(tmp_path, remote_name=remote_name)
        except Exception:
            _L.exception(f"trying to upload {src_path} but failed")
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

    if len(remote_name.encode("utf-8")) > _LINUX_NAME_MAX:
        remote_name = _shorten_remote_name(src_path, remote_name)

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
    rv = re.search(r"\[(\d+)\]$", name)
    if rv is None:
        raise ValueError(f"unexpected name: {name}")
    return rv.group(1)


def _shorten_remote_name(src_path: Path, original: str) -> str:
    _L.warning(f"remote name too long, will shorten: {original!r}")
    suffix = ".7z"
    try:
        gid = _get_gid_from_name(src_path.name)
        gid_part = f" [{gid}]{suffix}"
        title = _read_title_from_meta(src_path)
        candidate = f"{title}{gid_part}"
        if len(candidate.encode("utf-8")) <= _LINUX_NAME_MAX:
            return candidate
        max_title_bytes = _LINUX_NAME_MAX - len(gid_part.encode("utf-8"))
        title = (
            title.encode("utf-8")[:max_title_bytes]
            .decode("utf-8", errors="ignore")
            .rstrip()
        )
        return f"{title}{gid_part}"
    except Exception:
        _L.exception("could not build shortened name, falling back to gid-only")
    try:
        return f"{_get_gid_from_name(src_path.name)}{suffix}"
    except Exception:
        return original.encode("utf-8")[:_LINUX_NAME_MAX].decode(
            "utf-8", errors="ignore"
        )
