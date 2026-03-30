import logging
from concurrent.futures import Executor
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path, PurePath
from typing import override

from wcpan.drive.cli.lib import (
    create_drive_from_config,
    create_executor,
    get_file_hash,
    get_media_info,
    get_mime_type,
)
from wcpan.drive.core.exceptions import NodeNotFoundError
from wcpan.drive.core.lib import dispatch_change, upload_file_from_local
from wcpan.drive.core.types import Drive, Node

from ..dvd import DvdClient, create_dvd_client
from ..settings import DvdData, UploadData
from ._core import StorageBackend, UploadError


_L = logging.getLogger(__name__)


class DriveBackend(StorageBackend[Node]):
    def __init__(
        self,
        *,
        pool: Executor,
        drive: Drive,
        dvd_client: DvdClient,
        upload_to: PurePath,
    ) -> None:
        self._pool = pool
        self._drive = drive
        self._dvd = dvd_client
        self._upload_to = upload_to

    @override
    async def get_root_folder(self) -> Node:
        return await self._drive.get_node_by_path(self._upload_to)

    @override
    async def get_child(self, name: str, parent: Node) -> Node | None:
        try:
            return await self._drive.get_child_by_name(name, parent)
        except NodeNotFoundError:
            return None

    @override
    async def create_folder(self, name: str, parent: Node) -> Node:
        return await self._drive.create_directory(name, parent)

    @override
    async def upload_file(self, local_path: Path, parent: Node, *, name: str) -> Node:
        mime_type = get_mime_type(local_path)
        media_info = get_media_info(local_path)
        child = await upload_file_from_local(
            self._drive,
            local_path,
            parent,
            name=name,
            mime_type=mime_type,
            media_info=media_info,
        )
        if not child:
            raise UploadError(f"upload failed for {name}")
        if not child.hash:
            raise UploadError(f"{name} has invalid hash after upload")
        return child

    @override
    async def verify_file(
        self, local_path: Path, entry: Node, remote_path: PurePath
    ) -> None:
        if not entry.hash:
            raise UploadError(f"{remote_path} has invalid hash")
        local_hash = await get_file_hash(
            local_path, drive=self._drive, pool=self._pool, node=entry
        )
        if local_hash != entry.hash:
            raise UploadError(
                f"(remote) {remote_path} has a different hash ({local_hash}, {entry.hash})"
            )

    @override
    async def resolve_path(self, entry: Node) -> PurePath:
        return await self._drive.resolve_path(entry)

    @override
    async def sync(self) -> None:
        count = 0
        nodes: list[Node] = []
        async for change in self._drive.sync():
            count += 1
            dispatch_change(
                change,
                on_remove=lambda _: None,
                on_update=lambda _: nodes.append(_),
            )
        _L.info(f"sync {count}")
        try:
            await self._dvd.update_search_cache_by_nodes(nodes)
        except Exception:
            _L.exception("failed to update dvd search cache")

    @override
    async def ensure_entry_exists(self, entry: Node) -> None:
        while True:
            try:
                await self._drive.resolve_path(entry)
                break
            except NodeNotFoundError:
                _L.info("not in cache")
            except Exception:
                _L.exception("error on updating local cache")
            await self.sync()

    @override
    async def is_trashed(self, entry: Node) -> bool:
        return entry.is_trashed

    @override
    async def is_directory(self, entry: Node) -> bool:
        return entry.is_directory


@asynccontextmanager
async def create_drive_backend(
    upload_data: UploadData,
    *,
    dvd_data: DvdData | None,
):
    kwargs = upload_data.kwargs or {}
    config_path = kwargs["config_path"]
    upload_to = PurePath(kwargs["upload_to"])

    async with AsyncExitStack() as stack:
        pool = stack.enter_context(create_executor())
        drive = await stack.enter_async_context(
            create_drive_from_config(Path(config_path))
        )
        dvd_client = await stack.enter_async_context(create_dvd_client(dvd_data))
        yield DriveBackend(
            pool=pool, drive=drive, dvd_client=dvd_client, upload_to=upload_to
        )
