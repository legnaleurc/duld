from contextlib import asynccontextmanager

from ..dfd import create_dfd_client
from ..settings import Data
from ._core import Uploader, UploadError
from ._core import create_uploader as _make_uploader


__all__ = ["create_uploader", "Uploader", "UploadError"]


@asynccontextmanager
async def create_uploader(cfg: Data):
    async with create_dfd_client(cfg.exclude) as dfd_client:
        match cfg.upload.type:
            case "drive":
                from ._drive import create_drive_backend

                async with create_drive_backend(cfg.upload) as backend:
                    yield _make_uploader(backend=backend, dfd_client=dfd_client)
            case "local":
                from ._local import create_local_backend

                backend = create_local_backend(cfg.upload)
                yield _make_uploader(backend=backend, dfd_client=dfd_client)
            case _:
                raise ValueError(f"unknown upload type: {cfg.upload.type}")
