import shutil
from contextlib import asynccontextmanager
from pathlib import Path, PurePath
from typing import override

from .dfd import create_dfd_client
from .settings import ExcludeData, UploadData
from .upload import StorageBackend, UploadError, Uploader, create_uploader


class LocalBackend(StorageBackend[Path]):
    def __init__(self, *, upload_to: Path) -> None:
        self._upload_to = upload_to

    @override
    async def get_root_folder(self) -> Path:
        return self._upload_to

    @override
    async def get_child(self, name: str, parent: Path) -> Path | None:
        child = parent / name
        return child if child.exists() else None

    @override
    async def create_folder(self, name: str, parent: Path) -> Path:
        child = parent / name
        child.mkdir(exist_ok=True)
        return child

    @override
    async def upload_file(self, local_path: Path, parent: Path, *, name: str) -> Path:
        dest = parent / name
        shutil.copy2(local_path, dest)
        return dest

    @override
    async def verify_file(
        self, local_path: Path, entry: Path, remote_path: PurePath
    ) -> None:
        local_size = local_path.stat().st_size
        remote_size = entry.stat().st_size
        if local_size != remote_size:
            raise UploadError(
                f"{remote_path} size mismatch: local={local_size}, remote={remote_size}"
            )

    @override
    async def resolve_path(self, entry: Path) -> PurePath:
        return PurePath(entry)

    @override
    async def sync(self) -> None:
        pass

    @override
    async def ensure_entry_exists(self, entry: Path) -> None:
        if not entry.exists():
            raise UploadError(f"{entry} does not exist")

    @override
    async def is_trashed(self, entry: Path) -> bool:
        return False

    @override
    async def is_directory(self, entry: Path) -> bool:
        return entry.is_dir()


@asynccontextmanager
async def create_local_uploader(
    upload_data: UploadData,
    *,
    exclude_data: ExcludeData | None,
):
    kwargs = upload_data.kwargs or {}
    upload_to = Path(kwargs["upload_to"])

    async with create_dfd_client(exclude_data) as dfd_client:
        backend = LocalBackend(upload_to=upload_to)
        uploader: Uploader = create_uploader(backend=backend, dfd_client=dfd_client)
        yield uploader
