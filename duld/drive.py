import asyncio
import logging
import re
from asyncio import Lock
from collections.abc import Awaitable
from concurrent.futures import Executor
from contextlib import AsyncExitStack, contextmanager, asynccontextmanager
from pathlib import Path, PurePath
from typing import TypedDict

import magic
from aiohttp import ClientSession
from wcpan.drive.cli.lib import (
    get_media_info,
    create_drive_from_config,
    get_file_hash,
    create_executor,
)
from wcpan.drive.core.types import Node, Drive
from wcpan.drive.core.lib import upload_file_from_local
from wcpan.drive.core.exceptions import NodeNotFoundError


RETRY_TIMES = 3
_L = logging.getLogger(__name__)


class FilterResponse(TypedDict):
    id: int
    regexp: str


class UploadError(Exception):
    pass


@asynccontextmanager
async def create_uploader(
    *,
    drive_config_path: str,
    exclude_pattern: list[str] | None,
    exclude_url: str | None,
):
    async with AsyncExitStack() as stack:
        pool = stack.enter_context(create_executor())
        path = Path(drive_config_path)
        drive = await stack.enter_async_context(create_drive_from_config(path))
        curl = await stack.enter_async_context(ClientSession())
        yield DriveUploader(
            pool=pool,
            drive=drive,
            curl=curl,
            exclude_pattern=exclude_pattern,
            exclude_url=exclude_url,
        )


class DriveUploader:
    def __init__(
        self,
        *,
        pool: Executor,
        drive: Drive,
        curl: ClientSession,
        exclude_pattern: list[str] | None,
        exclude_url: str | None,
    ):
        self._pool = pool
        self._curl = curl
        self._drive = drive
        self._exclude_pattern = [] if not exclude_pattern else exclude_pattern
        self._exclude_url = exclude_url
        self._jobs = set[Path | int]()
        self._sync_lock = Lock()

    async def upload_from_hah(self, remote_path: PurePath, local_path: Path) -> None:
        if local_path in self._jobs:
            _L.warning(f"{local_path} is still uploading")
            return

        exclude_pattern = await self._fetch_filters()

        with job_guard(self._jobs, local_path):
            await self._sync()
            node = await self._drive.get_node_by_path(remote_path)
            await self._upload(node, local_path, exclude_pattern=exclude_pattern)

    async def upload_from_torrent(
        self,
        remote_path: PurePath,
        torrent_id: int,
        torrent_root: str,
        root_items: list[str],
    ) -> None:
        if torrent_id in self._jobs:
            _L.warning(f"{torrent_id} is still uploading")
            return

        exclude_pattern = await self._fetch_filters()

        with job_guard(self._jobs, torrent_id):
            await self._sync()

            node = await self._drive.get_node_by_path(remote_path)

            # files/directories to be upload
            items = (Path(torrent_root, _) for _ in root_items)
            for item in items:
                await self._upload(node, item, exclude_pattern=exclude_pattern)

    async def _sync(self):
        async with self._sync_lock:
            await asyncio.sleep(1)
            count = 0
            async for _ in self._drive.sync():
                count += 1
            _L.info(f"sync {count}")

    async def _upload(
        self, node: Node, local_path: Path, *, exclude_pattern: list[re.Pattern[str]]
    ) -> None:
        if _should_exclude(local_path.name, exclude_pattern):
            _L.info(f"excluded {local_path}")
            return

        if not local_path.exists():
            _L.warning(f"cannot upload non-exist path {local_path}")
            return

        if local_path.is_dir():
            await self._upload_directory(
                node, local_path, exclude_pattern=exclude_pattern
            )
        else:
            await self._upload_file_retry(node, local_path)

    async def _upload_directory(
        self, node: Node, local_path: Path, *, exclude_pattern: list[re.Pattern[str]]
    ) -> None:
        assert self._drive

        if node.is_trashed:
            raise UploadError(f"{node.name} should not be trashed")

        dir_name = local_path.name

        # find or create remote directory
        try:
            child_node = await self._drive.get_child_by_name(dir_name, node)
        except NodeNotFoundError:
            # create if not exists
            child_node = await self._drive.create_directory(dir_name, node)

        if child_node.is_trashed:
            raise UploadError(f"{child_node.name} should not be trashed")

        if not child_node.is_directory:
            # should be a directory
            raise UploadError(f"{child_node.name} should be a folder")

        # Need to update local cache for the added folder.
        # In theory we should pass remote path instead of doing this.
        await self._ensure_node_exists(child_node)

        for child_path in local_path.iterdir():
            await self._upload(child_node, child_path, exclude_pattern=exclude_pattern)

    async def _upload_file_retry(self, node: Node, local_path: Path) -> None:
        for _ in range(RETRY_TIMES):
            try:
                await self._upload_file(node, local_path)
                return
            except Exception:
                _L.exception("retry upload file")
            await self._sync()
        raise UploadError(f"tried upload {RETRY_TIMES} times")

    async def _upload_file(self, node: Node, local_path: Path) -> None:
        file_name = local_path.name
        remote_path = await self._drive.resolve_path(node)
        remote_path = remote_path / file_name

        child_node = await _else_none(self._drive.get_child_by_name(file_name, node))

        if child_node:
            if child_node.is_trashed:
                raise UploadError(f"{remote_path} already exists but it is in trash")

            if child_node.is_directory:
                raise UploadError(f"{remote_path} already exists but it is a folder")

            if not child_node.hash:
                raise UploadError(f"{remote_path} has invalid hash")

            # check integrity
            await self._verify_remote_file(local_path, remote_path, child_node.hash)
            _L.info(f"{remote_path} already exists and is the same file")
            return

        mime_type = _get_mime_type(local_path)
        media_info = await get_media_info(local_path)
        child_node = await upload_file_from_local(
            self._drive,
            local_path,
            node,
            mime_type=mime_type,
            media_info=media_info,
        )

        if not child_node:
            raise UploadError(f"{remote_path} upload failed")

        if not child_node.hash:
            raise UploadError(f"{remote_path} has invalid hash")

        # check integrity
        await self._verify_remote_file(
            local_path,
            remote_path,
            child_node.hash,
        )
        _L.info(f"finished {remote_path}")

    async def _verify_remote_file(
        self,
        local_path: Path,
        remote_path: PurePath,
        remote_hash: str,
    ) -> None:
        local_hash = await get_file_hash(local_path, drive=self._drive, pool=self._pool)
        if local_hash != remote_hash:
            raise UploadError(
                f"(remote) {remote_path} has a different hash ({local_hash}, {remote_hash})"
            )

    # used in exception handler, DO NOT throw another exception again
    async def _try_resolve_name_confliction(self, node: Node, local_path: Path):
        name = local_path.name
        child = await self._drive.get_child_by_name(name, node)
        if not child:
            return True
        try:
            await self._drive.move(node, trashed=True)
            return True
        except Exception:
            _L.exception(f"failed to resolve name confliction")
        return False

    async def _fetch_filters(self) -> list[re.Pattern[str]]:
        exclude_list = self._exclude_pattern

        if self._exclude_url:
            async with self._curl.get(self._exclude_url) as res:
                rv: list[FilterResponse] = await res.json()
                exclude_list = exclude_list + [_["regexp"] for _ in rv]

        return _to_regex_list(exclude_list)

    async def _ensure_node_exists(self, node: Node) -> None:
        while True:
            try:
                await self._drive.resolve_path(node)
                break
            except NodeNotFoundError:
                _L.info(f"not in cache")
            except Exception:
                _L.exception(f"error on updating local cache")
            await self._sync()


@contextmanager
def job_guard[T](set_: set[T], token: T):
    set_.add(token)
    try:
        yield
    finally:
        set_.discard(token)


async def _else_none(aw: Awaitable[Node]) -> Node | None:
    try:
        return await aw
    except NodeNotFoundError:
        return None


def _should_exclude(name: str, exclude_list: list[re.Pattern[str]]) -> bool:
    return any(_.match(name) is not None for _ in exclude_list)


def _to_regex_list(pattern_list: list[str]) -> list[re.Pattern[str]]:
    non_empty = (_ for _ in pattern_list if _)
    maybe_regex = (_to_pattern(_) for _ in non_empty)
    return [_ for _ in maybe_regex if _]


def _to_pattern(pattern: str) -> re.Pattern[str] | None:
    try:
        return re.compile(pattern, re.I)
    except Exception:
        return None


def _get_mime_type(file_path: Path) -> str:
    return magic.from_file(file_path, mime=True)  # type: ignore
