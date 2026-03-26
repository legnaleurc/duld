import asyncio
import logging
from abc import ABCMeta, abstractmethod
from asyncio import Lock, as_completed
from contextlib import contextmanager
from pathlib import Path, PurePath
from typing import Protocol

from .dfd import DfdClient, FilterList, should_exclude
from .processors import compress_context


RETRY_TIMES = 3
_L = logging.getLogger(__name__)


class UploadError(Exception):
    pass


class StorageBackend[E](metaclass=ABCMeta):
    @abstractmethod
    async def get_root_folder(self) -> E: ...

    @abstractmethod
    async def get_child(self, name: str, parent: E) -> E | None: ...

    @abstractmethod
    async def create_folder(self, name: str, parent: E) -> E: ...

    @abstractmethod
    async def upload_file(self, local_path: Path, parent: E, *, name: str) -> E: ...

    @abstractmethod
    async def verify_file(
        self, local_path: Path, entry: E, remote_path: PurePath
    ) -> None: ...

    @abstractmethod
    async def resolve_path(self, entry: E) -> PurePath: ...

    @abstractmethod
    async def sync(self) -> None: ...

    @abstractmethod
    async def ensure_entry_exists(self, entry: E) -> None: ...

    @abstractmethod
    async def is_trashed(self, entry: E) -> bool: ...

    @abstractmethod
    async def is_directory(self, entry: E) -> bool: ...


class Uploader(Protocol):
    async def upload_from_hah(self, local_path: Path, *, remote_name: str) -> None: ...

    async def upload_from_torrent(
        self, torrent_id: int, torrent_root: str, root_items: list[str]
    ) -> None: ...

    async def upload_from_path(self, local_path: Path) -> None: ...


def create_uploader[E](
    *, backend: StorageBackend[E], dfd_client: DfdClient
) -> "_DefaultUploader[E]":
    return _DefaultUploader(backend=backend, dfd_client=dfd_client)


class _DefaultUploader[E]:
    def __init__(
        self,
        *,
        backend: StorageBackend[E],
        dfd_client: DfdClient,
    ) -> None:
        self._backend = backend
        self._dfd = dfd_client
        self._jobs = set[Path | int]()
        self._sync_lock = Lock()

    async def upload_from_hah(self, local_path: Path, *, remote_name: str) -> None:
        if local_path in self._jobs:
            _L.warning(f"{local_path} is still uploading")
            return

        with job_guard(self._jobs, local_path):
            await self._sync()
            entry = await self._backend.get_root_folder()
            await self._upload_file_retry(entry, local_path, remote_name=remote_name)

    async def upload_from_torrent(
        self,
        torrent_id: int,
        torrent_root: str,
        root_items: list[str],
    ) -> None:
        if torrent_id in self._jobs:
            _L.warning(f"{torrent_id} is still uploading")
            return

        filters = await self._dfd.fetch_filters()

        with job_guard(self._jobs, torrent_id):
            await self._sync()

            entry = await self._backend.get_root_folder()

            src_list = (Path(torrent_root, _) for _ in root_items)

            with compress_context() as compress_avif:
                pending_list = as_completed((compress_avif(_) for _ in src_list))

                async_list = (await _ for _ in pending_list)

                async for item in async_list:
                    await self._upload(entry, item, filters=filters)

    async def upload_from_path(self, local_path: Path) -> None:
        with job_guard(self._jobs, local_path):
            await self._sync()
            entry = await self._backend.get_root_folder()
            await self._upload(entry, local_path, filters=[])

    async def _sync(self) -> None:
        async with self._sync_lock:
            await asyncio.sleep(1)
            await self._backend.sync()

    async def _upload(self, entry: E, local_path: Path, *, filters: FilterList) -> None:
        if should_exclude(local_path.name, filters):
            _L.info(f"excluded {local_path}")
            return

        if not local_path.exists():
            _L.warning(f"cannot upload non-exist path {local_path}")
            return

        if not local_path.is_dir():
            await self._upload_file_retry(
                entry, local_path, remote_name=local_path.name
            )
            return

        child_entry = await self._upload_directory(entry, local_path)

        for child_path in local_path.iterdir():
            await self._upload(child_entry, child_path, filters=filters)

    async def _upload_directory(self, entry: E, local_path: Path) -> E:
        if await self._backend.is_trashed(entry):
            raise UploadError(f"parent of {local_path.name} should not be trashed")

        dir_name = local_path.name

        child = await self._backend.get_child(dir_name, entry)
        if child is None:
            child = await self._backend.create_folder(dir_name, entry)

        if await self._backend.is_trashed(child):
            raise UploadError(f"{dir_name} should not be trashed")

        if not await self._backend.is_directory(child):
            raise UploadError(f"{dir_name} should be a folder")

        await self._backend.ensure_entry_exists(child)

        return child

    async def _upload_file_retry(
        self, entry: E, local_path: Path, *, remote_name: str
    ) -> None:
        for _ in range(RETRY_TIMES):
            try:
                await self._upload_file(entry, local_path, remote_name=remote_name)
                return
            except Exception:
                _L.exception("retry upload file")
            await self._sync()
        raise UploadError(f"tried upload {RETRY_TIMES} times")

    async def _upload_file(
        self, entry: E, local_path: Path, *, remote_name: str
    ) -> None:
        remote_path = await self._backend.resolve_path(entry)
        remote_path = remote_path / remote_name

        child = await self._backend.get_child(remote_name, entry)

        if child is not None:
            if await self._backend.is_trashed(child):
                raise UploadError(f"{remote_path} already exists but it is in trash")

            if await self._backend.is_directory(child):
                raise UploadError(f"{remote_path} already exists but it is a folder")

            await self._backend.verify_file(local_path, child, remote_path)
            _L.info(f"{remote_path} already exists and is the same file")
            return

        child = await self._backend.upload_file(local_path, entry, name=remote_name)
        await self._backend.verify_file(local_path, child, remote_path)
        _L.info(f"finished {remote_path}")


@contextmanager
def job_guard[T](set_: set[T], token: T):
    set_.add(token)
    try:
        yield
    finally:
        set_.discard(token)
