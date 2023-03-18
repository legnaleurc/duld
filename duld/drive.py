import asyncio
from logging import getLogger
import re
from concurrent.futures import ProcessPoolExecutor
from contextlib import AsyncExitStack, contextmanager
from pathlib import Path, PurePath
from typing import TypeVar

import aiohttp
from wcpan.drive.cli.util import get_media_info
from wcpan.drive.core.abc import Hasher
from wcpan.drive.core.drive import DriveFactory, upload_from_local
from wcpan.drive.core.exceptions import CacheError
from wcpan.drive.core.types import Node


class UploadError(Exception):
    pass


RETRY_TIMES = 3


class DriveUploader:
    def __init__(self, exclude_pattern: list[str] | None, exclude_url: str | None):
        self._exclude_pattern = [] if not exclude_pattern else exclude_pattern
        self._exclude_url = exclude_url
        self._jobs = set()
        self._sync_lock = asyncio.Lock()
        self._drive = None
        self._curl = None
        self._pool = None
        self._raii = None

    async def __aenter__(self):
        async with AsyncExitStack() as stack:
            factory = DriveFactory()
            factory.load_config()
            self._pool = stack.enter_context(ProcessPoolExecutor())
            self._drive = await stack.enter_async_context(factory(pool=self._pool))
            self._curl = await stack.enter_async_context(aiohttp.ClientSession())
            self._raii = stack.pop_all()
        return self

    async def __aexit__(self, type_, exc, tb):
        assert self._raii
        await self._raii.aclose()
        self._drive = None
        self._curl = None
        self._pool = None
        self._raii = None

    async def upload_path(self, remote_path: Path, local_path: Path) -> None:
        assert self._drive

        if local_path in self._jobs:
            getLogger(__name__).warning(f"{local_path} is still uploading")
            return

        with job_guard(self._jobs, local_path):
            await self._sync()

            node = await self._drive.get_node_by_path(remote_path)
            if not node:
                raise UploadError(f"{remote_path} not found")

            await self._upload(node, local_path)

    async def upload_torrent(
        self,
        remote_path: PurePath,
        torrent_id: int,
        torrent_root: str,
        root_items: list[str],
    ) -> None:
        assert self._drive

        if torrent_id in self._jobs:
            getLogger(__name__).warning(f"{torrent_id} is still uploading")
            return

        with job_guard(self._jobs, torrent_id):
            await self._sync()

            node = await self._drive.get_node_by_path(remote_path)
            if not node:
                raise UploadError(f"{remote_path} not found")

            # files/directories to be upload
            items = map(lambda _: Path(torrent_root, _), root_items)
            for item in items:
                await self._upload(node, item)

    async def _sync(self):
        assert self._drive
        async with self._sync_lock:
            await asyncio.sleep(1)
            count = 0
            async for changes in self._drive.sync():
                count += 1
            getLogger(__name__).info(f"sync {count}")

    async def _upload(self, node: Node, local_path: Path) -> None:
        if await self._should_exclude(local_path.name):
            getLogger(__name__).info(f"excluded {local_path}")
            return

        if not local_path.exists():
            getLogger(__name__).warning(f"cannot upload non-exist path {local_path}")
            return

        if local_path.is_dir():
            await self._upload_directory(node, local_path)
        else:
            await self._upload_file_retry(node, local_path)

    async def _upload_directory(self, node: Node, local_path: Path) -> None:
        assert self._drive

        if node.trashed:
            raise UploadError(f"{node.name} should not be trashed")

        dir_name = local_path.name

        # find or create remote directory
        child_node = await self._drive.get_node_by_name_from_parent(dir_name, node)

        if not child_node:
            # create if not exists
            child_node = await self._drive.create_folder(node, dir_name)

        if child_node.trashed:
            raise UploadError(f"{child_node.name} should not be trashed")

        if child_node.is_file:
            # should not be a file
            raise UploadError(f"{child_node.name} should be a folder")

        # Need to update local cache for the added folder.
        # In theory we should pass remote path instead of doing this.
        await self._ensure_node_exists(child_node)

        for child_path in local_path.iterdir():
            await self._upload(child_node, child_path)

    async def _upload_file_retry(self, node: Node, local_path: Path) -> None:
        for _ in range(RETRY_TIMES):
            try:
                await self._upload_file(node, local_path)
                return
            except Exception:
                getLogger(__name__).exception("retry upload file")
            await self._sync()
        raise UploadError(f"tried upload {RETRY_TIMES} times")

    async def _upload_file(self, node: Node, local_path: Path) -> None:
        assert self._drive

        file_name = local_path.name
        remote_path = await self._drive.get_path(node)
        if not remote_path:
            raise UploadError(f"{node.name} not found")
        remote_path = remote_path / file_name

        child_node = await self._drive.get_node_by_name_from_parent(file_name, node)

        if child_node:
            if child_node.trashed:
                raise UploadError(f"{remote_path} already exists but it is in trash")

            if child_node.is_folder:
                raise UploadError(f"{remote_path} already exists but it is a folder")

            if not child_node.hash_:
                raise UploadError(f"{remote_path} has invalid hash")

            # check integrity
            await self._verify_remote_file(local_path, remote_path, child_node.hash_)
            getLogger(__name__).info(
                f"{remote_path} already exists and is the same file"
            )
            return

        media_info = await get_media_info(local_path)
        child_node = await upload_from_local(
            self._drive,
            node,
            local_path,
            media_info,
        )

        if not child_node:
            raise UploadError(f"{remote_path} upload failed")

        if not child_node.hash_:
            raise UploadError(f"{remote_path} has invalid hash")

        # check integrity
        await self._verify_remote_file(
            local_path,
            remote_path,
            child_node.hash_,
        )
        getLogger(__name__).info(f"finished {remote_path}")

    async def _verify_remote_file(
        self,
        local_path: Path,
        remote_path: PurePath,
        remote_hash: str,
    ) -> None:
        assert self._drive
        loop = asyncio.get_running_loop()
        hasher = await self._drive.get_hasher()
        local_hash = await loop.run_in_executor(
            self._pool,
            md5sum,
            hasher,
            local_path,
        )
        if local_hash != remote_hash:
            raise UploadError(
                f"(remote) {remote_path} has a different hash ({local_hash}, {remote_hash})"
            )

    # used in exception handler, DO NOT throw another exception again
    async def _try_resolve_name_confliction(self, node: Node, local_path: Path):
        assert self._drive
        name = local_path.name
        child = await self._drive.get_node_by_name_from_parent(name, node)
        if not child:
            return True
        try:
            await self._drive.trash_node_by_id(node.id_)
            return True
        except Exception:
            getLogger(__name__).exception(f"failed to resolve name confliction")
        return False

    async def _should_exclude(self, name: str):
        for pattern in self._exclude_pattern:
            if re.match(pattern, name, re.IGNORECASE):
                return True

        if self._exclude_url and self._curl:
            async with self._curl.get(self._exclude_url) as res:
                rv: dict[str, str] = await res.json()
                for _, pattern in rv.items():
                    if re.match(pattern, name, re.IGNORECASE):
                        return True

        return False

    async def _ensure_node_exists(self, node: Node) -> None:
        assert self._drive
        while True:
            try:
                await self._drive.get_path(node)
                break
            except CacheError:
                getLogger(__name__).info(f"not in cache")
            except Exception:
                getLogger(__name__).exception(f"error on updating local cache")
            await self._sync()


def md5sum(hasher: Hasher, path: Path):
    with path.open("rb") as fin:
        while True:
            chunk = fin.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


T = TypeVar("T")


@contextmanager
def job_guard(set_: set[T], token: T):
    set_.add(token)
    try:
        yield
    finally:
        set_.discard(token)
