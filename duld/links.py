from tempfile import TemporaryDirectory
from pathlib import Path, PurePath
from logging import getLogger

from aiohttp import ClientSession

from .drive import DriveUploader


_L = getLogger(__name__)


async def upload_from_url(
    url: str, name: str | None, /, *, upload_to: PurePath, uploader: DriveUploader
) -> None:
    if not name:
        name = url.split("/")[-1]
    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / name
        _L.debug(f"downloading {url} to {path}")
        async with ClientSession() as session:
            async with session.get(url) as resp:
                with path.open("wb") as f:
                    f.write(await resp.read())
        await uploader.upload_from_path(upload_to, path)
